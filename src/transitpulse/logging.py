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
    """Attach one stdout handler (idempotent) and apply the format to every root handler.

    Foreign handlers are kept on purpose: the Azure Functions worker installs its own root handler
    that forwards records to Application Insights, and it uses the handler's formatter for the
    message text, so giving it the JSON formatter is what makes ``AppTraces`` hold the JSON lines.
    Clearing the handlers (the first version did) silently dropped every log in the cloud.
    """
    root = logging.getLogger()
    formatter: logging.Formatter = (
        JsonFormatter()
        if fmt == "json"
        else logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    for h in [h for h in root.handlers if getattr(h, "_transitpulse", False)]:
        root.removeHandler(h)  # re-created below, bound to the current sys.stdout
    handler = logging.StreamHandler(sys.stdout)
    handler._transitpulse = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    for h in root.handlers:
        h.setFormatter(formatter)
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
