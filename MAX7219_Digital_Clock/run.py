import json
import logging
import os
import signal
from pathlib import Path
from urllib import error as url_error
from urllib import request as url_request

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

LOGGER = logging.getLogger(__name__)


def load_options():
    options_path = Path("/data/options.json")
    if not options_path.exists():
        return {}
    try:
        return json.loads(options_path.read_text(encoding="utf-8"))
    except Exception as exc:
        LOGGER.warning("Could not parse options.json: %s", exc)
        return {}


def _to_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return default


def _extract_mqtt_service_data(payload):
    candidates = []
    if isinstance(payload, dict):
        candidates.append(payload)
        if isinstance(payload.get("data"), dict):
            candidates.append(payload["data"])
        if isinstance(payload.get("result"), dict):
            candidates.append(payload["result"])
            if isinstance(payload["result"].get("data"), dict):
                candidates.append(payload["result"]["data"])

    for candidate in candidates:
        host = candidate.get("host")
        port = candidate.get("port")
        username = candidate.get("username")
        password = candidate.get("password")
        if any([host, port, username, password]):
            return {
                "host": host,
                "port": port,
                "username": username,
                "password": password,
            }
    return {}


def fetch_supervisor_mqtt_service(timeout=3):
    token = os.getenv("SUPERVISOR_TOKEN", "").strip()
    if not token:
        return {}

    try:
        if requests:
            response = requests.get(
                "http://supervisor/services/mqtt",
                headers={"Authorization": f"Bearer {token}"},
                timeout=timeout,
            )
            response.raise_for_status()
            payload = response.json()
        else:
            req = url_request.Request(
                "http://supervisor/services/mqtt",
                headers={"Authorization": f"Bearer {token}"},
                method="GET",
            )
            with url_request.urlopen(req, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        return _extract_mqtt_service_data(payload)
    except (Exception, url_error.URLError) as exc:
        LOGGER.info("Supervisor MQTT service lookup unavailable: %s", exc)
        return {}


def resolve_runtime_options(raw_options):
    options = dict(raw_options or {})
    mqtt_options = options.get("mqtt")
    if not isinstance(mqtt_options, dict):
        mqtt_options = {}

    auto_enabled = _to_bool(mqtt_options.get("auto", True), default=True)
    source = "manual"
    service_data = fetch_supervisor_mqtt_service() if auto_enabled else {}

    if service_data:
        for key in ("host", "port", "username", "password"):
            current_value = mqtt_options.get(key)
            if current_value in (None, "", 0):
                mqtt_options[key] = service_data.get(key)
        source = "supervisor_service"

    if not str(mqtt_options.get("host", "")).strip():
        mqtt_options["host"] = "core-mosquitto"
        if source == "manual":
            source = "default_host"

    if not mqtt_options.get("port"):
        mqtt_options["port"] = 1883

    mqtt_options["_source"] = source
    options["mqtt"] = mqtt_options
    return options


def main():
    from engine.core import DisplayEngine
    from engine.mqtt import MQTTHandler
    from engine.webui import start_webui

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    options = resolve_runtime_options(load_options())
    engine = DisplayEngine(settings=options)
    mqtt_handler = MQTTHandler(engine, settings=options)
    webui = None

    def shutdown_handler(signum, frame):
        _ = frame
        LOGGER.info("Signal %s received, shutting down", signum)
        engine.stop()

    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

    try:
        mqtt_handler.start()
        webui = start_webui(
            engine,
            mqtt_handler=mqtt_handler,
            host="0.0.0.0",
            port=int(options.get("web_port", 8099)),
        )
        engine.run()
    finally:
        if webui:
            webui.stop()
        mqtt_handler.stop()
        LOGGER.info("MAX7219 service stopped")


if __name__ == "__main__":
    main()