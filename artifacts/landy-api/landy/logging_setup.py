"""Structured JSON logging configuration.

Never use print() in server code — use the logger returned here.
Use req.state.log (set by request middleware) in route handlers, or
import `logger` for non-request code.
"""
import logging
import sys
import structlog


def configure_logging(log_level: str = "INFO") -> None:
    """Set up structlog with JSON output for production, pretty output for dev."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(log_level)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


# Module-level logger — import this in non-request code
logger = structlog.get_logger(__name__)
