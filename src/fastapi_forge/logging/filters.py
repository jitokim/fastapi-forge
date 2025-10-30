"""Logging filters for FastAPI Forge.

Filters for controlling log output based on level, content, or endpoint.
"""

import logging


class InfoFilter(logging.Filter):
    """Filter that passes only INFO and DEBUG level logs.

    Used for stdout to separate informational logs from warnings/errors.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno < logging.WARNING


class WarningAndAboveFilter(logging.Filter):
    """Filter that passes only WARNING and above level logs.

    Used for stderr to separate warnings/errors from informational logs.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno >= logging.WARNING


class HealthCheckFilter(logging.Filter):
    """Filter out health check endpoint logs to reduce noise.

    Filters out logs containing common health check paths:
    - /api/health/heartbeat
    - /api/_/health
    """

    def filter(self, record: logging.LogRecord) -> bool:
        # Cache getMessage() result to avoid redundant msg % args
        if not hasattr(record, '_cached_message'):
            record._cached_message = record.getMessage()

        if "/api/health/heartbeat" in record._cached_message or "/api/_/health" in record._cached_message:
            return False
        return True


class LangfuseFilter(logging.Filter):
    """Filter out noisy Langfuse library logs.

    Filters out common Langfuse log patterns that don't indicate actual issues:
    - "Unexpected event format: No trace id found in event"
    - "Langfuse was not able to parse the LLM model"
    - "Item exceeds size limit"
    """

    __ignore_logs = [
        "Unexpected event format: No trace id found in event",
        "Langfuse was not able to parse the LLM model",
        "Item exceeds size limit",
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        # Cache getMessage() result to avoid redundant msg % args
        if not hasattr(record, '_cached_message'):
            record._cached_message = record.getMessage()

        for pattern in self.__ignore_logs:
            if pattern in record._cached_message:
                return False
        return True


class LangchainFilter(logging.Filter):
    """Filter out noisy Langchain library logs.

    Filters out common Langchain log patterns that don't indicate actual issues:
    - "StopAsyncIteration"
    """

    __ignore_logs = [
        "StopAsyncIteration",
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        # Cache getMessage() result to avoid redundant msg % args
        if not hasattr(record, '_cached_message'):
            record._cached_message = record.getMessage()

        for pattern in self.__ignore_logs:
            if pattern in record._cached_message:
                return False
        return True


__all__ = [
    "InfoFilter",
    "WarningAndAboveFilter",
    "HealthCheckFilter",
    "LangfuseFilter",
    "LangchainFilter",
]
