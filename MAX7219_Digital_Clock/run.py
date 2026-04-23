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


def load_addon_version():
    candidates = [Path("/app/config.json"), Path(__file__).resolve().parent / "config.json"]
    for candidate in candidates:
        if not candidate.exists():
            continue
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
            version = str(payload.get("version", "")).strip()
            if version:
                return version
        except Exception:
            continue
    return "unknown"


def _to_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return default


def _safe_int(value, default):
    try:
        return int(value)
    except Exception:
        return default


def _version_tuple(value):
    text = str(value or "").strip()
    if text.startswith(("v", "V")):
        text = text[1:]
    parts = []
    for chunk in text.split("."):
        digits = ""
        for char in chunk:
            if char.isdigit():
                digits += char
            else:
                break
        if digits == "":
            parts.append(0)
        else:
            parts.append(int(digits))
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def is_newer_version(latest, current):
    if not latest or not current:
        return False
    return _version_tuple(latest) > _version_tuple(current)


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


def _extract_github_tag(payload):
    if not isinstance(payload, dict):
        return ""
    for key in ("tag_name", "name"):
        value = str(payload.get(key, "")).strip()
        if value:
            return value
    return ""


def fetch_github_latest_version(repo, timeout=3):
    repo_text = str(repo or "").strip().strip("/")
    if not repo_text or "/" not in repo_text:
        return ""

    url_latest = f"https://api.github.com/repos/{repo_text}/releases/latest"
    url_tags = f"https://api.github.com/repos/{repo_text}/tags"
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "max7219-addon"}

    try:
        if requests:
            response = requests.get(url_latest, headers=headers, timeout=timeout)
            if response.status_code == 200:
                tag = _extract_github_tag(response.json())
                if tag:
                    return tag
            tags_resp = requests.get(url_tags, headers=headers, timeout=timeout)
            if tags_resp.status_code == 200 and isinstance(tags_resp.json(), list) and tags_resp.json():
                return str(tags_resp.json()[0].get("name", "")).strip()
            return ""

        req = url_request.Request(url_latest, headers=headers, method="GET")
        with url_request.urlopen(req, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
            tag = _extract_github_tag(payload)
            if tag:
                return tag

        req_tags = url_request.Request(url_tags, headers=headers, method="GET")
        with url_request.urlopen(req_tags, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
            if isinstance(payload, list) and payload:
                return str(payload[0].get("name", "")).strip()
    except Exception as exc:
        LOGGER.info("GitHub version check unavailable: %s", exc)
    return ""


def resolve_runtime_options(raw_options):
    options = dict(raw_options or {})
    mqtt_options = options.get("mqtt")
    if not isinstance(mqtt_options, dict):
        mqtt_options = {}
    github_options = options.get("github")
    if not isinstance(github_options, dict):
        github_options = {}

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
    options["addon_version"] = load_addon_version()

    github_check_enabled = _to_bool(
        github_options.get("version_check", options.get("github_version_check", True)),
        default=True,
    )
    github_repo = str(github_options.get("repo", options.get("github_repo", "mirarus/ha-addons"))).strip()
    github_timeout = _safe_int(
        github_options.get("check_timeout", options.get("github_check_timeout", 3)),
        3,
    )

    latest_version = fetch_github_latest_version(github_repo, timeout=github_timeout) if github_check_enabled else ""
    options["addon_latest_version"] = latest_version or options["addon_version"]
    options["addon_update_available"] = is_newer_version(latest_version, options["addon_version"])
    options["addon_update_source"] = "github" if latest_version else "local"
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
            port=8099,
        )
        engine.run()
    finally:
        if webui:
            webui.stop()
        mqtt_handler.stop()
        LOGGER.info("MAX7219 service stopped")


if __name__ == "__main__":
    main()