import importlib
import sys

import structlog

VERSION = "1.0.0"

def configure_logging(log_level: str = "INFO") -> None:
    """
    Configures structlog for JSON Lines output per ANCHOR:Q11.
    """
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer()
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(importlib.import_module("logging"), log_level.upper()) if "importlib" in sys.modules else 20
        ),
        cache_logger_on_first_use=True,
    )

def healthcheck() -> bool:
    """Basic healthcheck used by Docker HEALTHCHECK instruction."""
    return True

def get_version() -> str:
    return VERSION
