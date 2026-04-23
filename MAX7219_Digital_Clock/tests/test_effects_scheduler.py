import datetime as dt
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.effects import Effects
from engine.scheduler import Scheduler, SchedulerError


class TestEffects(unittest.TestCase):
    def test_effect_normalization(self):
        self.assertEqual(Effects.normalize("blink"), "blink")
        self.assertEqual(Effects.normalize("unknown"), "static")

    def test_wave_render(self):
        rendered = Effects.render("wave", "HELLO", 1)
        self.assertTrue(len(rendered) > 0)


class TestScheduler(unittest.TestCase):
    def test_upsert_and_trigger(self):
        scheduler = Scheduler()
        scheduler.apply_command(
            {
                "id": "morning",
                "time": "08:00",
                "text": "HI",
                "mode": "text",
                "effect": "scroll",
                "duration": 120,
                "days": [0, 1, 2, 3, 4, 5, 6],
            }
        )
        now = dt.datetime(2026, 4, 23, 8, 0, 0)
        result = scheduler.tick(now)
        self.assertIsNotNone(result)
        self.assertEqual(result["text"], "HI")

    def test_invalid_time(self):
        scheduler = Scheduler()
        with self.assertRaises(SchedulerError):
            scheduler.apply_command({"time": "99:99", "text": "x"})


if __name__ == "__main__":
    unittest.main()
