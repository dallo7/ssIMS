"""Central logging configuration.

Configures the root logger once per process so every module can simply do::

    import logging
    log = logging.getLogger(__name__)
    log.info("hello")

and get a consistent format plus the level chosen at boot time.

Environment variables (all optional):

``CPI_LOG_LEVEL``
    ``DEBUG`` / ``INFO`` / ``WARNING`` / ``ERROR`` / ``CRITICAL``.
    Default: ``DEBUG`` in dev, ``INFO`` in production.

``CPI_LOG_JSON``
    ``1`` / ``true`` / ``yes`` to emit one JSON object per line (good for
    CloudWatch, Stackdriver, Loki ingestion). Default: plain text.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from logging import Formatter, LogRecord

_configured = False

# Keep Dash / Werkzeug / SQLAlchemy at WARNING unless the operator explicitly
# raises CPI_LOG_LEVEL, so normal INFO output isn't drowned by per-request logs.
_NOISY_LOGGERS = (
    "werkzeug",
    "sqlalchemy.engine",
    "sqlalchemy.pool",
    "urllib3",
    "asyncio",
)

# Fields the stdlib attaches to every LogRecord — everything else is treated
# as application-supplied ``extra=`` and serialized into the JSON payload.
_RESERVED_RECORD_FIELDS = frozenset(
    vars(LogRecord("", 0, "", 0, "", None, None)).keys()
) | {"message", "asctime"}


class _JsonFormatter(Formatter):
    def format(self, record: LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        for k, v in record.__dict__.items():
            if k not in _RESERVED_RECORD_FIELDS:
                try:
                    json.dumps(v)
                    payload[k] = v
                except TypeError:
                    payload[k] = repr(v)
        return json.dumps(payload, ensure_ascii=False)


def _resolve_level() -> int:
    raw = (os.environ.get("CPI_LOG_LEVEL") or "").strip().upper()
    if raw and hasattr(logging, raw):
        val = getattr(logging, raw)
        if isinstance(val, int):
            return val
    is_prod = os.environ.get("CPI_ENV", "").strip().lower() in ("production", "prod", "live")
    return logging.INFO if is_prod else logging.DEBUG


def _use_json() -> bool:
    return os.environ.get("CPI_LOG_JSON", "").strip().lower() in ("1", "true", "yes")


def configure_logging() -> None:
    """Idempotent: safe to call multiple times (e.g. gunicorn preload + worker)."""
    global _configured
    if _configured:
        return
    _configured = True

    level = _resolve_level()
    handler = logging.StreamHandler(stream=sys.stdout)
    if _use_json():
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(
            Formatter(
                fmt="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

    root = logging.getLogger()
    # Replace handlers on re-config (gunicorn may have installed its own).
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(handler)
    root.setLevel(level)

    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(max(level, logging.WARNING))


def get_logger(name: str) -> logging.Logger:
    """Convenience helper that also lazily configures logging on first use."""
    configure_logging()
    return logging.getLogger(name)
