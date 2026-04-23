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


if __name__ == "__main__":
    unittest.main()
