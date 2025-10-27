"""Logging configuration for FastAPI Forge.

Production-ready logging setup with:
- JSON formatters (generic or Datadog-optimized)
- stdout/stderr separation (INFO → stdout, WARNING+ → stderr)
- Gunicorn/Uvicorn handler isolation
- Health check filtering
- Noisy library filtering (Langfuse, Langchain, httpx)

Quick Start:
    from fastapi_forge.logging import configure_logging

    # Generic JSON (works with any platform)
    configure_logging(formatter="json")

    # Datadog-optimized (with APM correlation)
    configure_logging(formatter="datadog")

Environment Variables:
    LOG_LEVEL: Set log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
               Default: INFO
"""

import logging
import logging.config
import os
import sys
from typing import Dict, Any, Literal

from .formatters import JSONFormatter, DatadogJSONFormatter
from .filters import (
    InfoFilter,
    WarningAndAboveFilter,
    HealthCheckFilter,
    LangfuseFilter,
    LangchainFilter,
)


def get_logging_config(
    formatter: Literal["json", "datadog"] = "json"
) -> Dict[str, Any]:
    """Get logging configuration dictionary for logging.config.dictConfig().

    Returns a complete dictConfig-compatible configuration with:
    - JSON formatted logs (generic or Datadog-optimized)
    - stdout/stderr separation (INFO → stdout, WARNING+ → stderr)
    - Handler isolation (Gunicorn handlers ≠ Root handlers)
    - Health check filtering (no /api/_/health logs)
    - Noisy library filtering (Langfuse, Langchain, httpx)
    - Gunicorn access log disabled

    Args:
        formatter: Choose formatter type
            - "json" (default): Generic JSON formatter
              Works with: ELK, Splunk, Grafana Loki, CloudWatch, etc.
            - "datadog": Datadog-optimized formatter
              Includes: status, dd.trace_id, dd.span_id fields

    Returns:
        Configuration dict for logging.config.dictConfig()

    Environment Variables:
        LOG_LEVEL: Set log level (default: INFO)

    Example:
        import logging.config
        from fastapi_forge.logging import get_logging_config

        config = get_logging_config(formatter="json")
        logging.config.dictConfig(config)

        logger = logging.getLogger(__name__)
        logger.info("Application started")

    Note:
        Most users should use configure_logging() instead, which calls
        this function automatically and handles setup.
    """
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    # Select formatter class
    formatter_class = DatadogJSONFormatter if formatter == "datadog" else JSONFormatter

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {
                "()": formatter_class,
            },
        },
        "filters": {
            "info_only": {
                "()": InfoFilter,
            },
            "warning_and_above": {
                "()": WarningAndAboveFilter,
            },
            "health_check": {
                "()": HealthCheckFilter,
            },
            "langfuse": {
                "()": LangfuseFilter,
            },
            "langchain": {
                "()": LangchainFilter,
            },
        },
        # Handler isolation: Gunicorn and Root use independent handlers
        "handlers": {
            # Root/Application handlers
            "root_stdout": {
                "class": "logging.StreamHandler",
                "level": log_level,
                "formatter": "json",
                "filters": ["info_only", "langfuse", "langchain"],
                "stream": sys.stdout,
            },
            "root_stderr": {
                "class": "logging.StreamHandler",
                "level": "WARNING",
                "formatter": "json",
                "filters": ["warning_and_above", "langfuse", "langchain"],
                "stream": sys.stderr,
            },
            # Gunicorn handlers
            "gunicorn_stdout": {
                "class": "logging.StreamHandler",
                "level": log_level,
                "formatter": "json",
                "filters": ["info_only", "health_check"],
                "stream": sys.stdout,
            },
            "gunicorn_stderr": {
                "class": "logging.StreamHandler",
                "level": "WARNING",
                "formatter": "json",
                "filters": ["warning_and_above"],
                "stream": sys.stderr,
            },
        },
        "loggers": {
            # Gunicorn loggers (use Gunicorn handlers)
            "gunicorn.error": {
                "level": log_level,
                "handlers": ["gunicorn_stdout", "gunicorn_stderr"],
                "propagate": False,
            },
            "gunicorn.access": {
                "level": "CRITICAL",  # Disable access log
                "handlers": [],
                "propagate": False,
            },
            # httpx/httpcore (use Gunicorn handlers)
            "httpx": {
                "level": "WARNING",
                "handlers": ["gunicorn_stdout", "gunicorn_stderr"],
                "propagate": False,
            },
            "httpcore": {
                "level": "WARNING",
                "handlers": ["gunicorn_stdout", "gunicorn_stderr"],
                "propagate": False,
            },
            # uvicorn (use Gunicorn handlers)
            "uvicorn": {
                "level": "INFO",
                "handlers": ["gunicorn_stdout", "gunicorn_stderr"],
                "propagate": False,
            },
            "uvicorn.access": {
                "level": "INFO",
                "handlers": ["gunicorn_stdout", "gunicorn_stderr"],
                "propagate": False,
            },
            "uvicorn.error": {
                "level": "INFO",
                "handlers": ["gunicorn_stdout", "gunicorn_stderr"],
                "propagate": False,
            },
        },
        # Root logger (use Root handlers)
        "root": {
            "level": log_level,
            "handlers": ["root_stdout", "root_stderr"],
        },
    }


def _configure_logging(formatter: Literal["json", "datadog"] = "json"):
    """Internal function to apply logging configuration."""
    try:
        config = get_logging_config(formatter=formatter)
        logging.config.dictConfig(config)

        # Log configuration completion (only once)
        if not hasattr(_configure_logging, "_configured"):
            logger = logging.getLogger(__name__)
            logger.info(
                "FastAPI Forge logging configured",
                extra={
                    "worker_pid": os.getpid(),
                    "log_level": os.getenv("LOG_LEVEL", "INFO"),
                    "formatter": formatter,
                },
            )
            _configure_logging._configured = True

    except Exception as e:
        # Continue application even if configuration fails
        print(f"⚠️ Failed to configure logging: {e}", file=sys.stderr)


def configure_logging(formatter: Literal["json", "datadog"] = "json"):
    """Configure production-ready logging with JSON output.

    One-line setup for structured logging with automatic stdout/stderr separation,
    health check filtering, and handler isolation for Gunicorn/Uvicorn.

    Args:
        formatter: Choose formatter type
            - "json" (default): Generic JSON formatter
              Use with: ELK Stack, Splunk, Grafana Loki, CloudWatch, etc.
            - "datadog": Datadog-optimized formatter
              Use with: Datadog APM (includes trace correlation fields)

    Basic Usage:
        from fastapi_forge.logging import configure_logging

        # Generic JSON (default)
        configure_logging()
        # or explicitly
        configure_logging(formatter="json")

        # Datadog-optimized
        configure_logging(formatter="datadog")

    Complete Example (Generic):
        # main.py
        from fastapi import FastAPI
        from fastapi_forge.logging import configure_logging
        import logging

        configure_logging(formatter="json")

        logger = logging.getLogger(__name__)
        app = FastAPI()

        @app.get("/")
        def root():
            logger.info("Request received", extra={"user_id": "123"})
            return {"message": "Hello"}

    Complete Example (Datadog with ddtrace):
        # main.py
        from dotenv import load_dotenv
        load_dotenv()  # Load DD_SERVICE, DD_ENV, etc.

        # IMPORTANT: Import configure_logging BEFORE importing FastAPI
        # This ensures ddtrace patches logging first (when using ddtrace-run)
        from fastapi_forge.logging import configure_logging
        configure_logging(formatter="datadog")

        from fastapi import FastAPI
        app = FastAPI()

        # Run with: ddtrace-run gunicorn main:app -w 2 -k uvicorn.workers.UvicornWorker

    Datadog Environment Variables:
        DD_SERVICE=my-service           # Service name
        DD_ENV=production               # Environment
        DD_TRACE_ENABLED=true           # Enable APM tracing
        DD_TRACE_LOGS_INJECTION=true   # Inject trace IDs into logs

    General Environment Variables:
        LOG_LEVEL=INFO  # Set log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    Note:
        - Safe to call multiple times (only applies once per worker)
        - Health checks at /api/_/health are automatically filtered
        - Noisy libraries (Langfuse, Langchain, httpx) are filtered
    """
    _configure_logging(formatter=formatter)


__all__ = [
    "get_logging_config",
    "configure_logging",
]
