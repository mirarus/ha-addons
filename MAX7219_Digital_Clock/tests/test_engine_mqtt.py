import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.core import DisplayEngine
from engine.mqtt import MQTTHandler


class TestEngine(unittest.TestCase):
    def test_apply_commands(self):
        engine = DisplayEngine(settings={"brightness": 5})
        engine.apply_command("text", "HELLO")
        engine.apply_command("mode", "clock")
        engine.apply_command("effect", "invert")
        engine.apply_command("brightness", 12)

        state = engine.get_state()
        self.assertEqual(state["mode"], "clock")
        self.assertEqual(state["effect"], "invert")
        self.assertEqual(state["brightness"], 12)

    def test_schedule_command(self):
        engine = DisplayEngine()
        engine.apply_command(
            "schedule",
            {
                "id": "event-1",
                "time": "10:30",
                "text": "MEETING",
                "days": [1, 2, 3],
                "duration": 180,
            },
        )
        state = engine.get_state()
        self.assertEqual(len(state["schedules"]), 1)

    def test_spi_device_settings_reflected_in_state(self):
        engine = DisplayEngine(settings={"spi_port": 0, "spi_device": 1})
        state = engine.get_state()
        self.assertEqual(state["spi_port"], 0)
        self.assertEqual(state["spi_device"], 1)
        self.assertIn("CE1", state["cs_pin"])


class DummyEngine:
    def __init__(self):
        self.called = []

    def apply_command(self, command, payload):
        self.called.append((command, payload))
        return {"ok": True}

    def get_state(self):
        return {"mode": "text", "text": "x", "effect": "static", "brightness": 5, "speed": 0.1, "schedules": []}

    def get_health(self):
        return {"uptime": 1, "loop_count": 1, "last_frame_ms": 1, "error_count": 0}


class TestMQTTHandler(unittest.TestCase):
    def test_command_parsing(self):
        handler = MQTTHandler(DummyEngine(), settings={"mqtt": {"namespace": "mirarus/max7219"}})
        self.assertEqual(handler._command_from_topic("mirarus/max7219/cmnd/text"), "text")
        self.assertEqual(handler._parse_payload("brightness", "15"), 15)

    def test_auto_broker_resolution(self):
        handler = MQTTHandler(DummyEngine(), settings={"mqtt": {"auto": True, "host": "", "port": 1883}})
        host, port = handler._resolve_broker()
        self.assertEqual(host, "core-mosquitto")
        self.assertEqual(port, 1883)

    def test_connection_status_snapshot(self):
        handler = MQTTHandler(DummyEngine(), settings={"mqtt": {"namespace": "mirarus/max7219"}})
        status = handler.get_connection_status()
        self.assertIn("connected", status)
        self.assertIn("reason", status)

    def test_discovery_entries(self):
        handler = MQTTHandler(
            DummyEngine(),
            settings={
                "mqtt": {
                    "namespace": "mirarus/max7219",
                    "discovery": True,
                    "discovery_prefix": "homeassistant",
                },
                "device_id": "max7219_display",
            },
        )
        entries = handler._discovery_entries()
        self.assertGreaterEqual(len(entries), 5)
        first_topic, first_payload = entries[0]
        self.assertTrue(first_topic.startswith("homeassistant/"))
        self.assertIn("device", first_payload)
        self.assertEqual(first_payload["device"]["identifiers"], ["max7219_display"])

    def test_legacy_flat_keys_still_supported(self):
        handler = MQTTHandler(
            DummyEngine(),
            settings={
                "mqtt_namespace": "legacy/max7219",
                "mqtt_discovery": False,
            },
        )
        self.assertEqual(handler.topics["cmnd_root"], "legacy/max7219/cmnd")
        self.assertFalse(handler.discovery_enabled)

    def test_disconnect_callback_v1_and_v2_signature(self):
        handler = MQTTHandler(DummyEngine(), settings={"mqtt": {"namespace": "mirarus/max7219"}})
        handler.connected_event.set()
        handler._on_disconnect(None, None, 5)
        self.assertFalse(handler.connected_event.is_set())

        handler.connected_event.set()
        handler._on_disconnect(None, None, 0, 7, None)
        self.assertFalse(handler.connected_event.is_set())

    def test_telemetry_interval_uses_nested_config(self):
        handler = MQTTHandler(
            DummyEngine(),
            settings={"mqtt": {"namespace": "mirarus/max7219"}, "telemetry": {"enabled": True, "interval": 42}},
        )
        self.assertEqual(handler._telemetry_interval(), 42)

    def test_publish_update_event_payload(self):
        handler = MQTTHandler(
            DummyEngine(),
            settings={
                "mqtt": {"namespace": "mirarus/max7219"},
                "addon_version": "2.4.0",
                "addon_latest_version": "2.5.0",
                "addon_update_available": True,
                "addon_update_source": "github",
            },
        )
        captured = {}

        def fake_publish(topic, payload, retain=False):
            captured["topic"] = topic
            captured["payload"] = payload
            captured["retain"] = retain

        handler._safe_publish = fake_publish
        handler.publish_update_event(event="startup")
        self.assertEqual(captured["topic"], "mirarus/max7219/tele/update")
        self.assertEqual(captured["payload"]["version"], "2.4.0")
        self.assertEqual(captured["payload"]["latest_version"], "2.5.0")
        self.assertTrue(captured["payload"]["update_available"])
        self.assertEqual(captured["payload"]["update_source"], "github")
        self.assertEqual(captured["payload"]["event"], "startup")
        self.assertTrue(captured["retain"])


if __name__ == "__main__":
    unittest.main()
