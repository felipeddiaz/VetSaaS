import json
import logging

_BASE_RECORD_KEYS = frozenset(vars(logging.LogRecord("", 0, "", 0, "", (), None)))


class RBACStructuredFormatter(logging.Formatter):
    """
    Formatter para eventos RBAC — emite una línea JSON por evento.
    Incluye los campos extra pasados via logger.warning("EVENT", extra={...}).
    Compatible con Datadog, ELK, y cualquier agregador que ingeste JSON por línea.
    """

    def format(self, record: logging.LogRecord) -> str:
        data = {
            "event": record.getMessage(),
            "level": record.levelname,
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%SZ"),
        }
        for key, val in vars(record).items():
            if key not in _BASE_RECORD_KEYS and not key.startswith("_"):
                data[key] = val
        return json.dumps(data, default=str)
