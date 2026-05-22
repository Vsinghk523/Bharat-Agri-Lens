"""Structured logging for the inference service.

Mirrors ``apps/api/app/logging.py`` so log lines from both services share
the same JSON shape — easier to grep through Railway's combined log
output. ``structlog`` is already a base dependency (see pyproject.toml),
so this file adds zero runtime cost; it's just the wiring.

Loaded by ``real_predictor.py`` to log model-download / prediction
events. Other modules (predictor.py, main.py) currently use FastAPI's
own logging path; they can swap to this when convenient.
"""

from __future__ import annotations

import logging
import sys

import structlog


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level.upper(),
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper())
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)  # type: ignore[no-any-return]
