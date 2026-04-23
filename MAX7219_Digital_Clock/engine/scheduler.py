import copy
import datetime as dt
import threading
import uuid


class SchedulerError(ValueError):
    pass


def _parse_hhmm(value):
    text = str(value or "").strip()
    try:
        return dt.datetime.strptime(text, "%H:%M").time()
    except ValueError as exc:
        raise SchedulerError("time must be in HH:MM format") from exc


class Scheduler:
    def __init__(self):
        self._lock = threading.Lock()
        self._events = {}
        self._last_trigger = {}
        self._active = None

    def list_events(self):
        with self._lock:
            items = [copy.deepcopy(event) for event in self._events.values()]
        return sorted(items, key=lambda event: (event["time"], event["id"]))

    def clear(self):
        with self._lock:
            self._events.clear()
            self._last_trigger.clear()
            self._active = None

    def delete(self, event_id):
        with self._lock:
            removed = self._events.pop(str(event_id), None)
            self._last_trigger.pop(str(event_id), None)
            if self._active and self._active.get("source_id") == str(event_id):
                self._active = None
        return bool(removed)

    def replace(self, items):
        if not isinstance(items, list):
            raise SchedulerError("schedule payload must contain an items list")
        prepared = {}
        for item in items:
            event = self._normalize_event(item)
            prepared[event["id"]] = event
        with self._lock:
            self._events = prepared
            self._last_trigger.clear()
            self._active = None
        return self.list_events()

    def upsert(self, item):
        event = self._normalize_event(item)
        with self._lock:
            self._events[event["id"]] = event
        return copy.deepcopy(event)

    def apply_command(self, payload):
        if not isinstance(payload, dict):
            raise SchedulerError("schedule payload must be a JSON object")

        action = str(payload.get("action", "upsert")).strip().lower()
        if action == "clear":
            self.clear()
            return {"action": "clear", "items": []}
        if action == "delete":
            event_id = payload.get("id")
            if not event_id:
                raise SchedulerError("delete action requires an id")
            deleted = self.delete(event_id)
            return {"action": "delete", "deleted": deleted, "items": self.list_events()}
        if action in {"set", "replace"}:
            items = self.replace(payload.get("items", []))
            return {"action": "set", "items": items}
        if action in {"list", "get"}:
            return {"action": "list", "items": self.list_events()}

        event_payload = payload.get("event", payload)
        event = self.upsert(event_payload)
        return {"action": "upsert", "event": event, "items": self.list_events()}

    def tick(self, now):
        if not isinstance(now, dt.datetime):
            now = dt.datetime.now()

        with self._lock:
            if self._active and now < self._active["expires_at"]:
                return copy.deepcopy(self._active["state"])
            self._active = None

            for event in self._events.values():
                if not event.get("enabled", True):
                    continue
                if now.weekday() not in event["days"]:
                    continue

                event_time = _parse_hhmm(event["time"])
                if (now.hour, now.minute) != (event_time.hour, event_time.minute):
                    continue

                minute_key = now.strftime("%Y%m%d%H%M")
                trigger_key = f"{event['id']}:{minute_key}"
                if self._last_trigger.get(event["id"]) == trigger_key:
                    continue

                self._last_trigger[event["id"]] = trigger_key
                state = {
                    "text": event["text"],
                    "mode": event["mode"],
                    "effect": event["effect"],
                    "brightness": event["brightness"],
                }
                self._active = {
                    "source_id": event["id"],
                    "state": state,
                    "expires_at": now + dt.timedelta(seconds=event["duration"]),
                }
                return copy.deepcopy(state)
        return None

    def _normalize_event(self, payload):
        if not isinstance(payload, dict):
            raise SchedulerError("event must be an object")

        event_id = str(payload.get("id") or uuid.uuid4())
        time_value = str(payload.get("time") or "").strip()
        if not time_value:
            raise SchedulerError("event requires time")
        _parse_hhmm(time_value)

        days_payload = payload.get("days", [0, 1, 2, 3, 4, 5, 6])
        if not isinstance(days_payload, list) or not days_payload:
            raise SchedulerError("days must be a non-empty list")

        days = []
        for day in days_payload:
            day_int = int(day)
            if day_int < 0 or day_int > 6:
                raise SchedulerError("day values must be between 0 and 6")
            days.append(day_int)

        duration = int(payload.get("duration", 60))
        if duration < 1 or duration > 3600:
            raise SchedulerError("duration must be between 1 and 3600 seconds")

        brightness = int(payload.get("brightness", 5))
        brightness = max(0, min(255, brightness))

        return {
            "id": event_id,
            "time": time_value,
            "text": str(payload.get("text", " ")),
            "mode": str(payload.get("mode", "text")).strip().lower() or "text",
            "effect": str(payload.get("effect", "static")).strip().lower() or "static",
            "brightness": brightness,
            "duration": duration,
            "enabled": bool(payload.get("enabled", True)),
            "days": sorted(set(days)),
        }
