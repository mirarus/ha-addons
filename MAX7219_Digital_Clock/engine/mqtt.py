import json
import logging
import threading
import time

try:
    import paho.mqtt.client as mqtt
except ImportError:  # pragma: no cover
    mqtt = None

LOGGER = logging.getLogger(__name__)


class _NoopClient:
    def username_pw_set(self, username, password=None):
        _ = (username, password)

    def will_set(self, topic, payload=None, qos=0, retain=False):
        _ = (topic, payload, qos, retain)

    def loop_start(self):
        return None

    def loop_stop(self):
        return None

    def connect(self, host, port, keepalive=60):
        _ = (host, port, keepalive)
        return 0

    def disconnect(self):
        return 0

    def subscribe(self, topic, qos=0):
        _ = (topic, qos)
        return (0, 1)

    def publish(self, topic, payload=None, qos=0, retain=False):
        _ = (topic, payload, qos, retain)
        return None


class MQTTHandler:
    def __init__(self, engine, settings=None):
        self.engine = engine
        self.settings = settings or {}
        self.stop_event = threading.Event()
        self.connected_event = threading.Event()
        self.telemetry_thread = None

        base_namespace = str(self.settings.get("mqtt_namespace", "mirarus/max7219")).strip("/")
        self.topics = {
            "cmnd": f"{base_namespace}/cmnd/#",
            "cmnd_root": f"{base_namespace}/cmnd",
            "stat_state": f"{base_namespace}/stat/state",
            "tele_health": f"{base_namespace}/tele/health",
        }

        self.client = mqtt.Client() if mqtt else _NoopClient()
        if not mqtt:
            LOGGER.warning("paho-mqtt unavailable, MQTT running in noop mode")
        username = str(self.settings.get("mqtt_username") or "").strip()
        password = str(self.settings.get("mqtt_password") or "").strip()
        if username:
            self.client.username_pw_set(username, password=password)

        self.client.will_set(
            self.topics["tele_health"],
            payload=json.dumps({"status": "offline"}),
            qos=1,
            retain=True,
        )
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

    def start(self):
        host = str(self.settings.get("mqtt_host", "core-mosquitto"))
        port = int(self.settings.get("mqtt_port", 1883))

        self.client.loop_start()
        self._connect_with_retry(host, port)
        self.telemetry_thread = threading.Thread(target=self._telemetry_loop, daemon=True)
        self.telemetry_thread.start()

    def stop(self):
        self.stop_event.set()
        try:
            self.publish_health(status="offline")
            self.client.loop_stop()
            self.client.disconnect()
        except Exception:  # pragma: no cover
            LOGGER.exception("MQTT stop failed")

    def _connect_with_retry(self, host, port):
        backoff = 1.0
        while not self.stop_event.is_set():
            try:
                self.client.connect(host, port, keepalive=30)
                return
            except Exception as exc:
                LOGGER.warning("MQTT connect failed (%s), retrying in %.1fs", exc, backoff)
                time.sleep(backoff)
                backoff = min(backoff * 2, 30.0)

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        _ = (userdata, flags, properties)
        if reason_code != 0:
            LOGGER.warning("MQTT connected with non-zero code: %s", reason_code)
            return
        LOGGER.info("MQTT connected, subscribing to %s", self.topics["cmnd"])
        self.connected_event.set()
        client.subscribe(self.topics["cmnd"], qos=1)
        self.publish_state()
        self.publish_health(status="online")

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties=None):
        _ = (client, userdata, disconnect_flags, properties)
        self.connected_event.clear()
        if self.stop_event.is_set():
            return
        LOGGER.warning("MQTT disconnected with code %s", reason_code)

    def _decode_payload(self, payload_bytes):
        return payload_bytes.decode("utf-8", errors="replace").strip()

    def _command_from_topic(self, topic):
        suffix = topic.replace(f"{self.topics['cmnd_root']}/", "", 1)
        return suffix.split("/")[-1].strip().lower()

    def _parse_payload(self, command, payload):
        if command == "brightness":
            return int(payload)
        if command == "schedule":
            return json.loads(payload) if payload else {"action": "list"}
        if command in {"mode", "effect"}:
            return payload.lower()
        return payload

    def _on_message(self, client, userdata, msg):
        _ = (client, userdata)
        payload_raw = self._decode_payload(msg.payload)
        command = self._command_from_topic(msg.topic)
        try:
            if command not in {"text", "mode", "effect", "brightness", "schedule"}:
                LOGGER.warning("Ignoring unsupported command topic: %s", msg.topic)
                return
            parsed = self._parse_payload(command, payload_raw)
            self.engine.apply_command(command, parsed)
            self.publish_state()
        except Exception as exc:
            LOGGER.warning("MQTT command failed (%s): %s", command, exc)
            self.publish_health(status="error", extra={"error": str(exc), "command": command})

    def publish_state(self):
        state = self.engine.get_state()
        payload = {
            "status": "online",
            "mode": state.get("mode"),
            "text": state.get("text"),
            "effect": state.get("effect"),
            "brightness": state.get("brightness"),
            "speed": state.get("speed"),
            "schedules": state.get("schedules", []),
        }
        self._safe_publish(self.topics["stat_state"], payload, retain=True)

    def publish_health(self, status="online", extra=None):
        health = self.engine.get_health()
        payload = {
            "status": status,
            "uptime": health.get("uptime"),
            "loop_count": health.get("loop_count"),
            "last_frame_ms": health.get("last_frame_ms"),
            "error_count": health.get("error_count"),
        }
        if extra:
            payload.update(extra)
        self._safe_publish(self.topics["tele_health"], payload, retain=True)

    def _safe_publish(self, topic, payload, retain=False):
        if not self.connected_event.is_set():
            return
        try:
            self.client.publish(topic, json.dumps(payload), qos=1, retain=retain)
        except Exception:  # pragma: no cover
            LOGGER.exception("MQTT publish failed for %s", topic)

    def _telemetry_loop(self):
        interval = int(self.settings.get("telemetry_interval", 15))
        interval = max(5, min(300, interval))
        while not self.stop_event.is_set():
            self.publish_state()
            self.publish_health(status="online")
            self.stop_event.wait(interval)