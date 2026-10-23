from __future__ import annotations

import json
import logging

from transitpulse import logging as tplog


def test_configure_keeps_foreign_handlers_and_formats_them_as_json() -> None:
    root = logging.getLogger()
    captured: list[str] = []

    class Foreign(logging.Handler):  # stands in for the Azure Functions worker handler
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(self.format(record))

    foreign = Foreign()
    root.addHandler(foreign)
    try:
        tplog.configure("json")
        tplog.configure("json")  # idempotent: still exactly one own handler
        own = [h for h in root.handlers if getattr(h, "_transitpulse", False)]
        assert len(own) == 1 and foreign in root.handlers
        tplog.bind(run_id="r1", feed="vbb")
        logging.getLogger("t").info("hello", extra={"step": "x"})
        line = json.loads(captured[-1])
        assert line["msg"] == "hello" and line["run_id"] == "r1" and line["step"] == "x"
    finally:
        root.removeHandler(foreign)
        for h in [h for h in root.handlers if getattr(h, "_transitpulse", False)]:
            root.removeHandler(h)
        tplog.clear()
