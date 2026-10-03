"""Structured JSON logs (doc 01 §9): `data/logs/horizon.log` (rotating 5 × 5 MB) and the console.

Every line carries `request_id` while a request is being handled. The key is redacted from the message,
its arguments and exception text (NFR-12): any `sk-or-…` token becomes `sk-or-[REDACTED]`.
"""

from __future__ import annotations

import json
import logging
import re
from contextvars import ContextVar
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

KEY_RE = re.compile(r"sk-or-[A-Za-z0-9_\-]+")
REDACTED = "sk-or-[REDACTED]"
_HANDLER_TAG = "_horizon_handler"


def redact(text: str) -> str:
    return KEY_RE.sub(REDACTED, text)


class RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = None
        if record.exc_info:
            record.exc_text = redact(logging.Formatter().formatException(record.exc_info))
            record.exc_info = None
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out: dict[str, object] = {
            "at": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
        }
        rid = request_id_var.get()
        if rid:
            out["request_id"] = rid
        for k in ("session_id", "job_id", "message_id", "method", "path", "status", "ms"):
            v = getattr(record, k, None)
            if v is not None:
                out[k] = v
        if record.exc_text:
            out["exc"] = record.exc_text
        return redact(json.dumps(out, ensure_ascii=False))


def setup_logging(logs_dir: Path, level: str = "INFO") -> None:
    """Install the console and file handlers on the root logger (idempotent; re-run after a factory reset)."""
    root = logging.getLogger()
    close_file_logging()
    for h in list(root.handlers):
        if getattr(h, _HANDLER_TAG, False):
            root.removeHandler(h)
    logs_dir.mkdir(parents=True, exist_ok=True)
    fmt = JsonFormatter()
    redactor = RedactFilter()
    console = logging.StreamHandler()
    file = RotatingFileHandler(logs_dir / "horizon.log", maxBytes=5 * 1024 * 1024, backupCount=4, encoding="utf-8")
    for h in (console, file):
        h.setFormatter(fmt)
        h.addFilter(redactor)
        setattr(h, _HANDLER_TAG, True)
        root.addHandler(h)
    root.setLevel(level)


def close_file_logging() -> None:
    """Detach and close file handlers so Windows can delete `data/logs` (factory reset)."""
    root = logging.getLogger()
    for h in list(root.handlers):
        if getattr(h, _HANDLER_TAG, False) and isinstance(h, logging.FileHandler):
            root.removeHandler(h)
            h.close()
