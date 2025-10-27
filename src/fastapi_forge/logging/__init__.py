"""FastAPI Forge - Production-ready Logging.

Structured JSON logging with automatic stdout/stderr separation, health check filtering,
and support for any log aggregation platform (ELK, Splunk, Grafana, Datadog, etc.)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Quick Start
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Generic JSON (Default - Works with any platform):
    from fastapi_forge.logging import configure_logging

    configure_logging()  # Uses "json" formatter by default

Datadog-optimized (With APM trace correlation):
    from fastapi_forge.logging import configure_logging

    configure_logging(formatter="datadog")

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Complete Example
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    # main.py
    from fastapi import FastAPI
    from fastapi_forge.logging import configure_logging
    import logging

    # Setup logging
    configure_logging(formatter="json")

    # Use logger
    logger = logging.getLogger(__name__)
    app = FastAPI()

    @app.get("/")
    def root():
        logger.info("Request received", extra={"user_id": "123"})
        return {"status": "ok"}

    # Output:
    # {"timestamp":"2025-10-27T10:00:00.123Z","level":"INFO","logger":"__main__",
    #  "message":"Request received","user_id":"123"}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Advanced Usage
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Direct formatter usage:
    from fastapi_forge.logging import JSONFormatter, DatadogJSONFormatter
    import logging

    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())  # or DatadogJSONFormatter()

Custom configuration:
    from fastapi_forge.logging import get_logging_config
    import logging.config

    config = get_logging_config(formatter="json")
    # Modify config as needed
    config["handlers"]["console"]["level"] = "DEBUG"
    logging.config.dictConfig(config)

Custom filters:
    from fastapi_forge.logging import HealthCheckFilter
    import logging

    filter = HealthCheckFilter()
    handler.addFilter(filter)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Features
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✓ JSON structured logging (RFC 5424 compatible)
✓ Automatic stdout/stderr separation (INFO → stdout, WARNING+ → stderr)
✓ Progressive truncation (prevents oversized logs)
✓ Health check filtering (/api/_/health)
✓ Noisy library filtering (Langfuse, Langchain, httpx)
✓ Gunicorn/Uvicorn handler isolation
✓ Exception formatting with traceback
✓ Docker 16KB log size handling

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
API Reference
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Main API:
    configure_logging(formatter="json" | "datadog")
        Complete one-line setup for production logging

    get_logging_config(formatter="json" | "datadog") -> dict
        Get logging configuration dict for manual setup

Formatters:
    JSONFormatter
        Generic JSON formatter (works with any platform)

    DatadogJSONFormatter
        Datadog-optimized formatter (adds status, dd.trace_id, dd.span_id)

Filters:
    HealthCheckFilter       - Filter /api/_/health requests
    InfoFilter              - Pass only INFO level logs
    WarningAndAboveFilter   - Pass WARNING and above
    LangfuseFilter          - Filter Langfuse library logs
    LangchainFilter         - Filter Langchain library logs
"""

from .config import configure_logging, get_logging_config
from .filters import (
    InfoFilter,
    WarningAndAboveFilter,
    HealthCheckFilter,
    LangfuseFilter,
    LangchainFilter,
)
from .formatters import JSONFormatter, DatadogJSONFormatter

__all__ = [
    # Main API
    "configure_logging",
    "get_logging_config",
    # Formatters
    "JSONFormatter",
    "DatadogJSONFormatter",
    # Filters
    "InfoFilter",
    "WarningAndAboveFilter",
    "HealthCheckFilter",
    "LangfuseFilter",
    "LangchainFilter",
]
