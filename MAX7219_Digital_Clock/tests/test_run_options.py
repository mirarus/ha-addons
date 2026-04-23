import sys
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import run


class TestRunOptionResolution(unittest.TestCase):
    def test_auto_uses_supervisor_service_when_available(self):
        options = {
            "mqtt": {
                "auto": True,
                "host": "",
                "port": 1883,
                "username": "",
                "password": "",
            }
        }
        with patch.object(
            run,
            "fetch_supervisor_mqtt_service",
            return_value={
                "host": "192.168.1.20",
                "port": 1883,
                "username": "mqtt",
                "password": "mqtt",
            },
        ):
            resolved = run.resolve_runtime_options(options)
        mqtt = resolved["mqtt"]
        self.assertEqual(mqtt["host"], "192.168.1.20")
        self.assertEqual(mqtt["username"], "mqtt")
        self.assertEqual(mqtt["password"], "mqtt")
        self.assertEqual(mqtt["_source"], "supervisor_service")

    def test_auto_without_service_uses_defaults(self):
        options = {"mqtt": {"auto": True, "host": "", "port": 0}}
        with patch.object(run, "fetch_supervisor_mqtt_service", return_value={}):
            resolved = run.resolve_runtime_options(options)
        mqtt = resolved["mqtt"]
        self.assertEqual(mqtt["host"], "core-mosquitto")
        self.assertEqual(mqtt["port"], 1883)
        self.assertEqual(mqtt["_source"], "default_host")


if __name__ == "__main__":
    unittest.main()
