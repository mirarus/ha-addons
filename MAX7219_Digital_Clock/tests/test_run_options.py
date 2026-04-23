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

    def test_resolved_options_include_addon_version(self):
        options = {"mqtt": {"auto": False, "host": "core-mosquitto", "port": 1883}}
        with patch.object(run, "load_addon_version", return_value="9.9.9"):
            resolved = run.resolve_runtime_options(options)
        self.assertEqual(resolved["addon_version"], "9.9.9")

    def test_detects_newer_github_version(self):
        options = {
            "mqtt": {"auto": False, "host": "core-mosquitto", "port": 1883},
            "github": {
                "version_check": True,
                "repo": "mirarus/ha-addons",
                "check_timeout": 3,
            },
        }
        with patch.object(run, "load_addon_version", return_value="2.4.0"):
            with patch.object(run, "fetch_github_latest_version", return_value="v2.5.0"):
                resolved = run.resolve_runtime_options(options)
        self.assertEqual(resolved["addon_latest_version"], "v2.5.0")
        self.assertTrue(resolved["addon_update_available"])
        self.assertEqual(resolved["addon_update_source"], "github")

    def test_github_check_disabled_uses_local_version(self):
        options = {
            "mqtt": {"auto": False, "host": "core-mosquitto", "port": 1883},
            "github": {"version_check": False},
        }
        with patch.object(run, "load_addon_version", return_value="2.5.0"):
            resolved = run.resolve_runtime_options(options)
        self.assertEqual(resolved["addon_latest_version"], "2.5.0")
        self.assertFalse(resolved["addon_update_available"])
        self.assertEqual(resolved["addon_update_source"], "local")

    def test_legacy_flat_github_keys_still_supported(self):
        options = {
            "mqtt": {"auto": False, "host": "core-mosquitto", "port": 1883},
            "github_version_check": True,
            "github_repo": "mirarus/ha-addons",
            "github_check_timeout": 3,
        }
        with patch.object(run, "load_addon_version", return_value="2.4.0"):
            with patch.object(run, "fetch_github_latest_version", return_value="2.4.1"):
                resolved = run.resolve_runtime_options(options)
        self.assertTrue(resolved["addon_update_available"])
        self.assertEqual(resolved["addon_latest_version"], "2.4.1")


if __name__ == "__main__":
    unittest.main()
