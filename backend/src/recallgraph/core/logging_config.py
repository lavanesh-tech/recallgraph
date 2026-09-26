"""Structured logging via structlog (JSON by default, console renderer optional)."""

import logging
import sys
from typing import TextIO

import structlog
from structlog.types import Processor

from recallgraph.core.config import LogLevel


def configure_logging(level: LogLevel, json_output: bool, *, stream: TextIO | None = None) -> None:
    """Configure structlog. CLIs pass stream=sys.stderr so stdout stays machine-readable."""
    renderer: Processor = (
        structlog.processors.JSONRenderer() if json_output else structlog.dev.ConsoleRenderer()
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelNamesMapping()[level]),
        logger_factory=structlog.PrintLoggerFactory(file=stream or sys.stdout),
        cache_logger_on_first_use=False,
    )
