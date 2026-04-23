import json
import logging
import signal
from pathlib import Path

from engine.core import DisplayEngine
from engine.mqtt import MQTTHandler
from engine.webui import start_webui

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


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    options = load_options()
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