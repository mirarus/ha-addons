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
    CONNECT_REASON_TEXT = {
        1: "unacceptable protocol version",
        2: "identifier rejected",
        3: "broker unavailable",
        4: "bad username or password",
        5: "not authorized",
    }

    def __init__(self, engine, settings=None):
        self.engine = engine
        self.settings = settings or {}
        self.mqtt_settings = self.settings.get("mqtt") if isinstance(self.settings.get("mqtt"), dict) else {}
        self.telemetry_settings = self.settings.get("telemetry") if isinstance(self.settings.get("telemetry"), dict) else {}
        self.stop_event = threading.Event()
        self.connected_event = threading.Event()
        self.telemetry_thread = None
        self._status_lock = threading.Lock()

        base_namespace = str(self._mqtt_opt("namespace", "mqtt_namespace", "mirarus/max7219")).strip("/")
        self.topics = {
            "cmnd": f"{base_namespace}/cmnd/#",
            "cmnd_root": f"{base_namespace}/cmnd",
            "stat_state": f"{base_namespace}/stat/state",
            "tele_health": f"{base_namespace}/tele/health",
            "tele_update": f"{base_namespace}/tele/update",
        }
        self.addon_version = str(self.settings.get("addon_version", "unknown"))
        self.addon_latest_version = str(self.settings.get("addon_latest_version", self.addon_version))
        self.addon_update_available = bool(self.settings.get("addon_update_available", False))
        self.addon_update_source = str(self.settings.get("addon_update_source", "local"))
        self.discovery_enabled = self._to_bool(self._mqtt_opt("discovery", "mqtt_discovery", True))
        self.discovery_prefix = str(
            self._mqtt_opt("discovery_prefix", "mqtt_discovery_prefix", "homeassistant")
        ).strip("/") or "homeassistant"
        self.device_id = str(self.settings.get("device_id", "max7219_display")).strip() or "max7219_display"
        self.device_name = str(self.settings.get("device_name", "MAX7219 Display")).strip() or "MAX7219 Display"
        self._discovery_published = False
        self.mqtt_auto = self._to_bool(self._mqtt_opt("auto", "mqtt_auto", True))
        self.connection_status = {
            "connected": False,
            "code": None,
            "reason": "not_started",
            "host": None,
            "port": None,
            "auto": self.mqtt_auto,
            "credential_source": str(self.mqtt_settings.get("_source", "manual_or_defaults")),
            "last_error": "",
        }

        self.client = mqtt.Client() if mqtt else _NoopClient()
        if not mqtt:
            LOGGER.warning("paho-mqtt unavailable, MQTT running in noop mode")
        elif hasattr(self.client, "reconnect_delay_set"):
            # Keep reconnect responsive but avoid tight loops.
            min_delay = max(1, int(self._mqtt_opt("reconnect_min_delay", "mqtt_reconnect_min_delay", 1)))
            max_delay = max(min_delay, int(self._mqtt_opt("reconnect_max_delay", "mqtt_reconnect_max_delay", 8)))
            self.client.reconnect_delay_set(min_delay=min_delay, max_delay=max_delay)
        username = str(self._mqtt_opt("username", "mqtt_username", "") or "").strip()
        password = str(self._mqtt_opt("password", "mqtt_password", "") or "").strip()
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

    @staticmethod
    def _to_bool(value):
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return False

    def _mqtt_opt(self, nested_key, legacy_key, default=None):
        if nested_key in self.mqtt_settings:
            return self.mqtt_settings.get(nested_key)
        return self.settings.get(legacy_key, default)

    @staticmethod
    def _as_bool(value, default=True):
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return default

    def _telemetry_interval(self):
        raw = self.telemetry_settings.get("interval", self.settings.get("telemetry_interval", 15))
        interval = int(raw)
        return max(5, min(300, interval))

    def _resolve_broker(self):
        configured_host = str(self._mqtt_opt("host", "mqtt_host", "")).strip()
        if configured_host:
            host = configured_host
        elif self.mqtt_auto:
            host = "core-mosquitto"
        else:
            host = "core-mosquitto"
        port = int(self._mqtt_opt("port", "mqtt_port", 1883))
        return host, port

    def _update_connection_status(self, **kwargs):
        with self._status_lock:
            self.connection_status.update(kwargs)

    def get_connection_status(self):
        with self._status_lock:
            return dict(self.connection_status)

    def start(self):
        host, port = self._resolve_broker()
        self._update_connection_status(host=host, port=port, reason="connecting")

        self.client.loop_start()
        self._connect_with_retry(host, port)
        self.telemetry_thread = threading.Thread(target=self._telemetry_loop, daemon=True)
        self.telemetry_thread.start()

    def stop(self):
        self.stop_event.set()
        self._update_connection_status(connected=False, reason="stopping")
        try:
            self.publish_update_event(event="shutdown")
            self.publish_health(status="offline")
            self.client.loop_stop()
            self.client.disconnect()
            self._update_connection_status(connected=False, reason="stopped")
        except Exception:  # pragma: no cover
            LOGGER.exception("MQTT stop failed")

    def _connect_with_retry(self, host, port):
        backoff = float(self._mqtt_opt("initial_retry_delay", "mqtt_initial_retry_delay", 0.5))
        max_backoff = float(self._mqtt_opt("retry_max_delay", "mqtt_retry_max_delay", 5.0))
        backoff = max(0.2, min(backoff, max_backoff))
        while not self.stop_event.is_set():
            try:
                self.client.connect(host, port, keepalive=30)
                self._update_connection_status(reason="connect_called", last_error="")
                return
            except Exception as exc:
                self._update_connection_status(connected=False, reason="connect_exception", last_error=str(exc))
                LOGGER.warning("MQTT connect failed (%s), retrying in %.1fs", exc, backoff)
                time.sleep(backoff)
                backoff = min(backoff * 2, max_backoff)

    @staticmethod
    def _normalize_reason_code(reason_code):
        try:
            return int(reason_code)
        except Exception:
            return -1

    def _on_connect(self, client, userdata, flags, reason_code=0, properties=None):
        _ = (userdata, flags, properties)
        reason_code = self._normalize_reason_code(reason_code)
        if reason_code != 0:
            self.connected_event.clear()
            reason_text = self.CONNECT_REASON_TEXT.get(reason_code, "unknown connect error")
            self._update_connection_status(connected=False, code=reason_code, reason=reason_text)
            LOGGER.warning(
                "MQTT connect rejected (code=%s, reason=%s). Check mqtt_host/mqtt_port/mqtt_username/mqtt_password and broker ACLs.",
                reason_code,
                reason_text,
            )
            self.publish_health(
                status="error",
                extra={"error": f"mqtt_connect_rejected:{reason_code}", "reason": reason_text},
            )
            return
        LOGGER.info("MQTT connected, subscribing to %s", self.topics["cmnd"])
        self.connected_event.set()
        self._update_connection_status(connected=True, code=0, reason="connected", last_error="")
        client.subscribe(self.topics["cmnd"], qos=1)
        self.publish_discovery(force=not self._discovery_published)
        self.publish_update_event(event="startup")
        self.publish_state()
        self.publish_health(status="online")

    def _on_disconnect(self, client, userdata, *args):
        # paho v1: (client, userdata, rc)
        # paho v2: (client, userdata, disconnect_flags, reason_code, properties)
        reason_code = 0
        if len(args) == 1:
            reason_code = args[0]
        elif len(args) >= 2:
            reason_code = args[1]
        reason_code = self._normalize_reason_code(reason_code)
        _ = (client, userdata)
        self.connected_event.clear()
        reason_text = self.CONNECT_REASON_TEXT.get(reason_code, "disconnected")
        self._update_connection_status(connected=False, code=reason_code, reason=reason_text)
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
        enabled = self._as_bool(self.telemetry_settings.get("enabled", True), default=True)
        if not enabled:
            return
        interval = self._telemetry_interval()
        while not self.stop_event.is_set():
            self.publish_state()
            self.publish_health(status="online")
            self.stop_event.wait(interval)

    def publish_update_event(self, event="startup"):
        payload = {
            "status": "online" if self.connected_event.is_set() else "offline",
            "event": str(event),
            "version": self.addon_version,
            "latest_version": self.addon_latest_version,
            "update_available": self.addon_update_available,
            "update_source": self.addon_update_source,
            "device_id": self.device_id,
            "namespace": self.topics["cmnd_root"].rsplit("/cmnd", 1)[0],
        }
        self._safe_publish(self.topics["tele_update"], payload, retain=True)

    def _discovery_device(self):
        return {
            "identifiers": [self.device_id],
            "name": self.device_name,
            "manufacturer": "Mirarus",
            "model": "MAX7219 Raspberry Pi",
            "sw_version": "addon",
        }

    def _discovery_entries(self):
        device = self._discovery_device()
        state_topic = self.topics["stat_state"]
        availability_topic = self.topics["tele_health"]
        cmnd_root = self.topics["cmnd_root"]
        return [
            (
                f"{self.discovery_prefix}/text/{self.device_id}_text/config",
                {
                    "name": "MAX7219 Text",
                    "unique_id": f"{self.device_id}_text",
                    "object_id": f"{self.device_id}_text",
                    "command_topic": f"{cmnd_root}/text",
                    "state_topic": state_topic,
                    "value_template": "{{ value_json.text }}",
                    "availability_topic": availability_topic,
                    "availability_template": "{{ value_json.status }}",
                    "payload_available": "online",
                    "payload_not_available": "offline",
                    "device": device,
                },
            ),
            (
                f"{self.discovery_prefix}/select/{self.device_id}_mode/config",
                {
                    "name": "MAX7219 Mode",
                    "unique_id": f"{self.device_id}_mode",
                    "object_id": f"{self.device_id}_mode",
                    "command_topic": f"{cmnd_root}/mode",
                    "state_topic": state_topic,
                    "value_template": "{{ value_json.mode }}",
                    "options": ["text", "clock"],
                    "availability_topic": availability_topic,
                    "availability_template": "{{ value_json.status }}",
                    "payload_available": "online",
                    "payload_not_available": "offline",
                    "device": device,
                },
            ),
            (
                f"{self.discovery_prefix}/select/{self.device_id}_effect/config",
                {
                    "name": "MAX7219 Effect",
                    "unique_id": f"{self.device_id}_effect",
                    "object_id": f"{self.device_id}_effect",
                    "command_topic": f"{cmnd_root}/effect",
                    "state_topic": state_topic,
                    "value_template": "{{ value_json.effect }}",
                    "options": ["static", "scroll", "marquee", "blink", "invert", "wave"],
                    "availability_topic": availability_topic,
                    "availability_template": "{{ value_json.status }}",
                    "payload_available": "online",
                    "payload_not_available": "offline",
                    "device": device,
                },
            ),
            (
                f"{self.discovery_prefix}/number/{self.device_id}_brightness/config",
                {
                    "name": "MAX7219 Brightness",
                    "unique_id": f"{self.device_id}_brightness",
                    "object_id": f"{self.device_id}_brightness",
                    "command_topic": f"{cmnd_root}/brightness",
                    "state_topic": state_topic,
                    "value_template": "{{ value_json.brightness }}",
                    "min": 0,
                    "max": 255,
                    "step": 1,
                    "mode": "box",
                    "availability_topic": availability_topic,
                    "availability_template": "{{ value_json.status }}",
                    "payload_available": "online",
                    "payload_not_available": "offline",
                    "device": device,
                },
            ),
            (
                f"{self.discovery_prefix}/sensor/{self.device_id}_mqtt_status/config",
                {
                    "name": "MAX7219 MQTT Status",
                    "unique_id": f"{self.device_id}_mqtt_status",
                    "object_id": f"{self.device_id}_mqtt_status",
                    "state_topic": availability_topic,
                    "value_template": "{{ value_json.status }}",
                    "json_attributes_topic": availability_topic,
                    "device": device,
                },
            ),
        ]

    def publish_discovery(self, force=False):
        if not self.discovery_enabled:
            return
        if self._discovery_published and not force:
            return
        for topic, payload in self._discovery_entries():
            self._safe_publish(topic, payload, retain=True)
        self._discovery_published = True