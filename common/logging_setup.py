import json
import logging
from datetime import datetime, timezone


class JsonLineFormatter(logging.Formatter):
    _standard_fields = set(logging.makeLogRecord({}).__dict__) | {
        "message",
        "asctime",
    }

    def format(self, record):
        event = getattr(record, "event", record.getMessage())
        payload = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "component": getattr(record, "component", record.name),
            "thread": record.threadName,
            "event": event,
        }
        for key, value in record.__dict__.items():
            if key not in self._standard_fields and key not in payload and not key.startswith("_"):
                payload[key] = value
        return json.dumps(payload, default=str, separators=(",", ":"))


def configure_logging():
    root = logging.getLogger()
    if not getattr(root, "_p3_json_logging", False):
        if not root.handlers:
            root.addHandler(logging.StreamHandler())
        for handler in root.handlers:
            handler.setFormatter(JsonLineFormatter())
        root.setLevel(logging.INFO)
        root._p3_json_logging = True
    logging.getLogger("pika").setLevel(logging.WARNING)
