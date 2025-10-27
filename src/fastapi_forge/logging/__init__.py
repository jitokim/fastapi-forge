"""Logging module for FastAPI Forge.

Production-ready logging configuration with Datadog optimization.

Quick Start:
    ```python
    from fastapi_forge.logging import configure_logging

    # Configure logging (call after ddtrace patching)
    configure_logging()
    ```

Advanced Usage:
    ```python
    from fastapi_forge.logging import (
        configure_logging,
        get_logging_config,
        JSONFormatter,
        HealthCheckFilter,
    )

    # Get configuration dict
    config = get_logging_config()

    # Use formatter directly
    formatter = JSONFormatter()

    # Use filters
    filter = HealthCheckFilter()
    ```
"""

from .config import configure_logging, get_logging_config
from .filters import (
    InfoFilter,
    WarningAndAboveFilter,
    HealthCheckFilter,
    LangfuseFilter,
    LangchainFilter,
)
from .formatters import JSONFormatter

__all__ = [
    # Main API
    "configure_logging",
    "get_logging_config",
    # Formatters
    "JSONFormatter",
    # Filters
    "InfoFilter",
    "WarningAndAboveFilter",
    "HealthCheckFilter",
    "LangfuseFilter",
    "LangchainFilter",
]
