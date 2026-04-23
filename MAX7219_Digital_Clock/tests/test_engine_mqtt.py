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
        handler = MQTTHandler(DummyEngine(), settings={"mqtt_namespace": "mirarus/max7219"})
        self.assertEqual(handler._command_from_topic("mirarus/max7219/cmnd/text"), "text")
        self.assertEqual(handler._parse_payload("brightness", "15"), 15)

    def test_auto_broker_resolution(self):
        handler = MQTTHandler(DummyEngine(), settings={"mqtt_auto": True, "mqtt_host": "", "mqtt_port": 1883})
        host, port = handler._resolve_broker()
        self.assertEqual(host, "core-mosquitto")
        self.assertEqual(port, 1883)

    def test_connection_status_snapshot(self):
        handler = MQTTHandler(DummyEngine(), settings={"mqtt_namespace": "mirarus/max7219"})
        status = handler.get_connection_status()
        self.assertIn("connected", status)
        self.assertIn("reason", status)

    def test_discovery_entries(self):
        handler = MQTTHandler(
            DummyEngine(),
            settings={
                "mqtt_namespace": "mirarus/max7219",
                "mqtt_discovery": True,
                "mqtt_discovery_prefix": "homeassistant",
                "device_id": "max7219_display",
            },
        )
        entries = handler._discovery_entries()
        self.assertGreaterEqual(len(entries), 5)
        first_topic, first_payload = entries[0]
        self.assertTrue(first_topic.startswith("homeassistant/"))
        self.assertIn("device", first_payload)
        self.assertEqual(first_payload["device"]["identifiers"], ["max7219_display"])

    def test_disconnect_callback_v1_and_v2_signature(self):
        handler = MQTTHandler(DummyEngine(), settings={"mqtt_namespace": "mirarus/max7219"})
        handler.connected_event.set()
        handler._on_disconnect(None, None, 5)
        self.assertFalse(handler.connected_event.is_set())

        handler.connected_event.set()
        handler._on_disconnect(None, None, 0, 7, None)
        self.assertFalse(handler.connected_event.is_set())


if __name__ == "__main__":
    unittest.main()
