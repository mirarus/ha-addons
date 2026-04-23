import json
import logging
from pathlib import Path
from threading import Thread

from flask import Flask, jsonify, render_template, request
from werkzeug.serving import make_server

LOGGER = logging.getLogger(__name__)


def _create_app(engine, mqtt_handler=None):
    template_dir = Path(__file__).resolve().parent.parent / "web"
    app = Flask(__name__, template_folder=str(template_dir))

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/health")
    def health():
        return jsonify({"ok": True, "health": engine.get_health()})

    @app.get("/api/state")
    def state():
        mqtt_status = mqtt_handler.get_connection_status() if mqtt_handler else {"reason": "disabled"}
        return jsonify({"state": engine.get_state(), "health": engine.get_health(), "mqtt": mqtt_status})

    @app.post("/api/command")
    def command():
        payload = request.get_json(silent=True) or {}
        cmd = payload.get("command")
        value = payload.get("value")
        if not cmd:
            return jsonify({"ok": False, "error": "command is required"}), 400

        try:
            result = engine.apply_command(cmd, value)
            if mqtt_handler:
                mqtt_handler.publish_state()
            return jsonify(result)
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @app.get("/api/schedules")
    def list_schedules():
        return jsonify({"items": engine.scheduler.list_events()})

    @app.post("/api/schedules")
    def apply_schedule():
        payload = request.get_json(silent=True)
        if not payload:
            return jsonify({"ok": False, "error": "JSON payload required"}), 400
        try:
            result = engine.apply_command("schedule", payload)
            if mqtt_handler:
                mqtt_handler.publish_state()
            return jsonify(result)
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @app.delete("/api/schedules/<event_id>")
    def delete_schedule(event_id):
        deleted = engine.delete_schedule(event_id)
        if mqtt_handler:
            mqtt_handler.publish_state()
        return jsonify({"ok": True, "deleted": bool(deleted)})

    @app.post("/api/schedules/import")
    def import_schedules():
        payload = request.get_json(silent=True) or {}
        raw_items = payload.get("items")
        if raw_items is None and "text" in payload:
            try:
                raw_items = json.loads(payload["text"])
            except json.JSONDecodeError as exc:
                return jsonify({"ok": False, "error": str(exc)}), 400
        try:
            result = engine.apply_command("schedule", {"action": "set", "items": raw_items or []})
            if mqtt_handler:
                mqtt_handler.publish_state()
            return jsonify(result)
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    return app


class WebUIService:
    def __init__(self, engine, mqtt_handler=None, host="0.0.0.0", port=8099):
        self.app = _create_app(engine, mqtt_handler=mqtt_handler)
        self.host = host
        self.port = int(port)
        self._thread = None
        self._server = None

    def start(self):
        self._server = make_server(self.host, self.port, self.app)
        self._thread = Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        LOGGER.info("Web UI started at http://%s:%s", self.host, self.port)

    def stop(self):
        if self._server:
            self._server.shutdown()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        LOGGER.info("Web UI stopped")


def start_webui(engine, mqtt_handler=None, host="0.0.0.0", port=8099):
    service = WebUIService(engine, mqtt_handler=mqtt_handler, host=host, port=port)
    service.start()
    return service