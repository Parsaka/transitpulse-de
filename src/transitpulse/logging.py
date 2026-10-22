"""Structured logging: one JSON object per line, ready for Log Analytics / Grafana Loki.

Every record carries ``run_id`` and ``feed`` when set through :func:`bind`. No extra dependency:
the formatter is a few lines of stdlib code, which also keeps the Azure Function cold start short.
"""

from __future__ import annotations

import contextvars
import json
import logging
import sys
import time
from datetime import UTC, datetime
from typing import Any

_context: contextvars.ContextVar[dict[str, Any]] = contextvars.ContextVar("tp_log_ctx")

_RESERVED = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        payload.update(_context.get({}))
        payload.update({k: v for k, v in record.__dict__.items() if k not in _RESERVED})
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


def configure(fmt: str = "text", level: int = logging.INFO) -> None:
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    if fmt == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(handler)
    root.setLevel(level)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def bind(**fields: Any) -> None:
    """Attach fields (run_id, feed, ...) to every record emitted in this context."""
    _context.set({**_context.get({}), **fields})


def clear() -> None:
    _context.set({})


class Timed:
    """``with Timed(log, "parse") as t:`` logs the step duration and lets the body add fields."""

    def __init__(self, log: logging.Logger, step: str) -> None:
        self.log, self.step = log, step
        self.fields: dict[str, Any] = {}
        self.duration_ms = 0.0

    def __enter__(self) -> Timed:
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, *exc: object) -> None:
        self.duration_ms = round((time.perf_counter() - self._t0) * 1000, 1)
        self.log.info(
            "step %s done",
            self.step,
            extra={"step": self.step, "duration_ms": self.duration_ms, **self.fields},
        )
