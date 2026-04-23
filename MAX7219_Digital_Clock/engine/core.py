import copy
import datetime as dt
import logging
from pathlib import Path
import threading
import time

try:
    from luma.core.interface.serial import noop, spi
    from luma.core.render import canvas
    from luma.led_matrix.device import max7219
except ImportError:  # pragma: no cover
    max7219 = None
    spi = None
    noop = None
    canvas = None

from engine.effects import Effects
from engine.scheduler import Scheduler, SchedulerError

LOGGER = logging.getLogger(__name__)


class _FallbackDevice:
    def __init__(self):
        self._contrast = 5

    def contrast(self, value):
        self._contrast = int(value)


class DisplayEngine:
    SUPPORTED_MODES = {"text", "clock"}

    def __init__(self, settings=None):
        settings = settings or {}
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self.scheduler = Scheduler()
        self.effects = Effects()

        self.state = {
            "text": str(settings.get("default_text", "HELLO")),
            "mode": str(settings.get("default_mode", "text")).strip().lower() or "text",
            "effect": Effects.normalize(settings.get("default_effect", "static")),
            "speed": self._clamp_float(settings.get("speed", 0.15), 0.02, 5.0),
            "brightness": self._clamp_int(settings.get("brightness", 5), 0, 255),
        }
        if self.state["mode"] not in self.SUPPORTED_MODES:
            self.state["mode"] = "text"

        self.metrics = {
            "started_at": time.time(),
            "last_frame_ms": 0.0,
            "loop_count": 0,
            "error_count": 0,
            "last_error": "",
        }
        self._frame = 0
        self.spi_port = self._clamp_int(settings.get("spi_port", 0), 0, 1)
        self.spi_device = self._clamp_int(settings.get("spi_device", 0), 0, 1)
        self.device = self._build_device(settings)
        self.device.contrast(self.state["brightness"])

    def _build_device(self, settings):
        if not all((max7219, spi, noop)):
            LOGGER.warning("luma/spidev unavailable, running in fallback mode")
            return _FallbackDevice()

        cascaded = self._clamp_int(settings.get("cascaded", 4), 1, 16)
        block_orientation = self._clamp_int(settings.get("block_orientation", 90), -360, 360)
        rotate = self._clamp_int(settings.get("rotate", 0), 0, 3)

        try:
            serial = spi(port=self.spi_port, device=self.spi_device, gpio=noop())
            return max7219(
                serial,
                cascaded=cascaded,
                block_orientation=block_orientation,
                rotate=rotate,
            )
        except Exception as exc:  # pragma: no cover
            LOGGER.exception("Hardware init failed, fallback mode enabled: %s", exc)
            self.metrics["error_count"] += 1
            self.metrics["last_error"] = str(exc)
            return _FallbackDevice()

    @staticmethod
    def _clamp_int(value, minimum, maximum):
        parsed = int(value)
        return max(minimum, min(maximum, parsed))

    @staticmethod
    def _clamp_float(value, minimum, maximum):
        parsed = float(value)
        return max(minimum, min(maximum, parsed))

    def stop(self):
        self._stop_event.set()

    def is_running(self):
        return not self._stop_event.is_set()

    def get_state(self):
        with self._lock:
            snapshot = copy.deepcopy(self.state)
        snapshot["schedules"] = self.scheduler.list_events()
        snapshot["spi_port"] = self.spi_port
        snapshot["spi_device"] = self.spi_device
        snapshot["cs_pin"] = "GPIO8 (CE0)" if self.spi_device == 0 else "GPIO7 (CE1)"
        return snapshot

    def get_health(self):
        with self._lock:
            metrics = copy.deepcopy(self.metrics)
        metrics["uptime"] = int(time.time() - metrics["started_at"])
        metrics["running"] = self.is_running()
        return metrics

    def set(self, key, value):
        key = str(key).strip().lower()
        with self._lock:
            if key == "text":
                self.state["text"] = str(value)
            elif key == "mode":
                mode = str(value).strip().lower()
                if mode not in self.SUPPORTED_MODES:
                    raise ValueError("mode must be text or clock")
                self.state["mode"] = mode
            elif key == "effect":
                self.state["effect"] = Effects.normalize(value)
            elif key == "brightness":
                brightness = self._clamp_int(value, 0, 255)
                self.state["brightness"] = brightness
                self.device.contrast(brightness)
            elif key == "speed":
                self.state["speed"] = self._clamp_float(value, 0.02, 5.0)
            else:
                raise ValueError(f"unsupported state key: {key}")
            return copy.deepcopy(self.state)

    def apply_schedule_command(self, payload):
        return self.scheduler.apply_command(payload)

    def delete_schedule(self, event_id):
        return self.scheduler.delete(event_id)

    def apply_command(self, command, payload):
        command = str(command).strip().lower()
        if command in {"text", "mode", "effect", "brightness", "speed"}:
            self.set(command, payload)
            return {"ok": True, "state": self.get_state()}
        if command == "schedule":
            result = self.apply_schedule_command(payload)
            return {"ok": True, "result": result, "state": self.get_state()}
        raise ValueError(f"unsupported command: {command}")

    def _resolve_text(self, state_snapshot, now):
        mode = state_snapshot.get("mode", "text")
        if mode == "clock":
            return now.strftime("%H:%M")
        return str(state_snapshot.get("text", " "))

    def _draw_text(self, text):
        if canvas is None:
            return
        with canvas(self.device) as draw:
            draw.text((0, 0), text, fill="white")

    def run_pin_diagnostics(self):
        selected_dev = f"/dev/spidev{self.spi_port}.{self.spi_device}"
        checks = {
            "spi_enabled": Path("/dev/spidev0.0").exists() or Path("/dev/spidev0.1").exists(),
            "selected_device_path": selected_dev,
            "selected_device_exists": Path(selected_dev).exists(),
            "cs_pin": "GPIO8 (CE0)" if self.spi_device == 0 else "GPIO7 (CE1)",
            "driver_loaded": all((max7219, spi, noop)),
            "render_backend": "luma" if canvas is not None else "fallback",
        }

        warnings = []
        notes = []
        if not checks["spi_enabled"]:
            warnings.append("SPI interface disabled or /dev/spidev* not exposed")
        if not checks["selected_device_exists"]:
            warnings.append(f"Selected SPI device not found: {selected_dev}")
        if not checks["driver_loaded"]:
            warnings.append("luma/spidev python modules unavailable")

        software_path_healthy = checks["spi_enabled"] and checks["selected_device_exists"] and checks["driver_loaded"]
        if software_path_healthy:
            notes.append(
                "Software SPI path looks healthy. If display is still blank, verify DIN/CLK/CS/VCC/GND wiring and CE0/CE1 selection."
            )

        return {
            "ok": software_path_healthy,
            "checks": checks,
            "warnings": warnings,
            "notes": notes,
        }

    def run(self):
        LOGGER.info("DisplayEngine loop started")
        while not self._stop_event.is_set():
            started = time.time()
            try:
                now = dt.datetime.now()
                schedule_override = self.scheduler.tick(now)
                with self._lock:
                    state_snapshot = copy.deepcopy(self.state)
                    metrics_ref = self.metrics

                if schedule_override:
                    state_snapshot.update(schedule_override)

                base_text = self._resolve_text(state_snapshot, now)
                rendered_text = self.effects.render(
                    state_snapshot.get("effect", "static"),
                    base_text,
                    self._frame,
                )
                self._draw_text(rendered_text)

                elapsed_ms = (time.time() - started) * 1000.0
                with self._lock:
                    metrics_ref["last_frame_ms"] = elapsed_ms
                    metrics_ref["loop_count"] += 1

                self._frame += 1
                delay = float(state_snapshot.get("speed", 0.15))
                self._stop_event.wait(delay)
            except SchedulerError as exc:
                LOGGER.warning("Scheduler command error: %s", exc)
                with self._lock:
                    self.metrics["error_count"] += 1
                    self.metrics["last_error"] = str(exc)
            except Exception as exc:  # pragma: no cover
                LOGGER.exception("Render loop error: %s", exc)
                with self._lock:
                    self.metrics["error_count"] += 1
                    self.metrics["last_error"] = str(exc)
                self._stop_event.wait(0.5)
        LOGGER.info("DisplayEngine loop stopped")