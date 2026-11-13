"""Standard `logging` with the request id on every line. Called once, from `main.py`:

    configure_logging(settings.log_level)

    2026-03-30 10:00:00,000 INFO [3f2a9c1d8e7b4a05] api.agent.router: ...

Swap the format for JSON (or for structlog) here, in one place, when you ship to a log collector.
"""

import logging
import sys

from .request_id import RequestIdFilter

FORMAT = "%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s"


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(FORMAT))
    handler.addFilter(RequestIdFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    for noisy in ("uvicorn.access", "httpx"):
        logging.getLogger(noisy).setLevel(max(logging.WARNING, root.level))
