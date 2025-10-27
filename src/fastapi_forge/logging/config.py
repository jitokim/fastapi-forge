"""Logging configuration for FastAPI Forge.

Production-ready logging configuration with Gunicorn/Uvicorn support.
"""

import logging
import logging.config
import os
import sys
from typing import Dict, Any

from .formatters import JSONFormatter
from .filters import (
    InfoFilter,
    WarningAndAboveFilter,
    HealthCheckFilter,
    LangfuseFilter,
    LangchainFilter,
)


def get_logging_config() -> Dict[str, Any]:
    """Get logging configuration dictionary.

    Returns a dictConfig-compatible configuration for production logging:
    - JSON formatted logs (Datadog/ELK/Splunk compatible)
    - stdout/stderr separation (INFO → stdout, WARNING+ → stderr)
    - Handler isolation (Gunicorn ↔ Root independent)
    - Filters for health checks and noisy libraries
    - Gunicorn access log disabled

    Returns:
        Dict containing logging configuration

    Environment Variables:
        LOG_LEVEL: Log level (default: INFO)
    """
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {
                "()": JSONFormatter,
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
                "level": "INFO",
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
                "level": "INFO",
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


def _configure_logging():
    """Internal function to apply logging configuration."""
    try:
        config = get_logging_config()
        logging.config.dictConfig(config)

        # Log configuration completion (only once)
        if not hasattr(_configure_logging, "_configured"):
            logger = logging.getLogger(__name__)
            logger.info(
                "FastAPI Forge logging configured",
                extra={
                    "worker_pid": os.getpid(),
                    "log_level": os.getenv("LOG_LEVEL", "INFO"),
                },
            )
            _configure_logging._configured = True

    except Exception as e:
        # Continue application even if configuration fails
        print(f"⚠️ Failed to configure logging: {e}", file=sys.stderr)


def configure_logging():
    """Configure logging for production use.

    Call this function explicitly for ddtrace compatibility.
    When using ddtrace-run, call this function AFTER ddtrace patches logging
    to ensure DD_TRACE_LOGS_INJECTION works correctly.

    Example:
        ```python
        # main.py
        from dotenv import load_dotenv
        load_dotenv()

        from fastapi_forge.logging import configure_logging

        # Configure logging after ddtrace patching
        configure_logging()

        from fastapi import FastAPI
        app = FastAPI()
        ```

    For Datadog APM integration:
        Set environment variables:
        - DD_SERVICE: Service name
        - DD_ENV: Environment (dev/staging/prod)
        - DD_TRACE_ENABLED: Enable tracing (true)
        - DD_TRACE_LOGS_INJECTION: Inject trace IDs (true)

    Note:
        This function can be safely called multiple times.
        The configuration will only be applied once per worker.
    """
    _configure_logging()


__all__ = [
    "get_logging_config",
    "configure_logging",
]
