"""JSON formatters for FastAPI Forge.

Provides two JSON formatters for structured logging:

1. JSONFormatter: Generic JSON formatter compatible with any log aggregation platform
   (ELK Stack, Splunk, Grafana Loki, CloudWatch, etc.)

2. DatadogJSONFormatter: Datadog-optimized formatter with trace correlation fields
   (dd.trace_id, dd.span_id, dd_service, dd_env, status)

Both formatters include:
- Progressive truncation strategy (3 stages)
- Individual field size limits
- Exception formatting with traceback truncation
- Docker 16KB log size consideration

Usage:
    # Direct usage
    from fastapi_forge.logging import JSONFormatter, DatadogJSONFormatter

    formatter = JSONFormatter()  # or DatadogJSONFormatter()
    handler.setFormatter(formatter)

    # Or use configure_logging() for automatic setup
    from fastapi_forge.logging import configure_logging

    configure_logging(formatter="json")     # Generic
    configure_logging(formatter="datadog")  # Datadog-optimized
"""

import json
import logging
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, Iterable


class JSONFormatter(logging.Formatter):
    """Generic JSON formatter for structured logging.

    Use this formatter for platform-agnostic JSON logging that works with
    any log aggregation system (ELK Stack, Splunk, Grafana Loki, CloudWatch, etc.)

    Output Format:
        {
            "timestamp": "2025-10-27T10:00:00.123Z",  # ISO8601 UTC with Z suffix
            "level": "INFO",                           # Log level
            "logger": "myapp.module",                  # Logger name
            "message": "User action completed",        # Log message
            "user_id": "12345",                        # Custom fields from 'extra'
            "exception": {...}                         # Exception info (if present)
        }

    Features:
        - 3-stage progressive truncation (field → non-core → message)
        - Field size limits (1KB per field, 15KB total)
        - Critical field preservation (trace_id, thread_id, component)
        - Exception formatting with traceback truncation (2KB limit)
        - JSON serialization error handling

    Example:
        import logging
        from fastapi_forge.logging import JSONFormatter

        handler = logging.StreamHandler()
        handler.setFormatter(JSONFormatter())
        logger = logging.getLogger(__name__)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        logger.info("User logged in", extra={"user_id": "123", "ip": "1.2.3.4"})
        # Output: {"timestamp":"...","level":"INFO","logger":"...","message":"User logged in","user_id":"123","ip":"1.2.3.4"}
    """

    # Core fields - order guaranteed for readability
    CORE_FIELDS = ["timestamp", "level", "logger", "message"]
    CRITICAL_FIELDS = {
        "trace_id",
        "thread_id",
        "component",
    }

    # Size limits - considering Docker 16KB limit
    MAX_MESSAGE_SIZE = 15000  # Safety margin included
    MAX_FIELD_SIZE = 1000  # Individual field size limit

    def format(self, record: logging.LogRecord) -> str:
        """Convert log record to structured JSON."""
        try:
            log_entry = self._build_core_structure(record)

            # Merge extra fields
            if hasattr(record, "__dict__"):
                extra_fields = self._extract_extra_fields(record)
                log_entry.update(extra_fields)

            # Handle exception info
            if record.exc_info:
                log_entry["exception"] = self._format_exception(record.exc_info)

            # JSON serialization and size check
            json_str = json.dumps(log_entry, ensure_ascii=False, separators=(",", ":"))

            return self._ensure_size_limit(json_str, log_entry)

        except Exception as e:
            # Fallback: output minimal log even if formatting fails
            return self._fallback_format(record, e)

    def _build_core_structure(self, record: logging.LogRecord) -> Dict[str, Any]:
        """Build core log structure."""
        # Use cached message if available (set by filters)
        if not hasattr(record, '_cached_message'):
            record._cached_message = record.getMessage()

        # Limit message size upfront to prevent _progressive_truncation overhead
        message = record._cached_message
        if len(message) > 10000:  # 10KB limit for message field
            message = message[:10000] + "...[truncated]"

        return {
            "timestamp": self._format_timestamp(record.created),
            "level": record.levelname,
            "logger": record.name,
            "message": message,
        }

    def _extract_extra_fields(self, record: logging.LogRecord) -> Dict[str, Any]:
        """Extract and clean extra fields."""
        # Exclude basic log record fields
        skip_fields = {
            "name",
            "msg",
            "args",
            "levelname",
            "levelno",
            "pathname",
            "filename",
            "module",
            "lineno",
            "funcName",
            "created",
            "msecs",
            "relativeCreated",
            "thread",
            "threadName",
            "processName",
            "process",
            "exc_info",
            "exc_text",
            "stack_info",
        }

        extra = {}
        for key, value in record.__dict__.items():
            if key not in skip_fields and not key.startswith("_"):
                # Clean value and apply size limit
                cleaned_value = self._clean_value(value)
                if cleaned_value is not None:
                    extra[key] = cleaned_value

        return extra

    def _clean_value(self, value: Any) -> Any:
        """Clean and apply size limits to values."""
        if value is None:
            return None

        # String size limit
        if isinstance(value, str):
            if len(value) > self.MAX_FIELD_SIZE:
                return value[: self.MAX_FIELD_SIZE] + "...[truncated]"
            return value

        # Check JSON serializability for dict/list
        if isinstance(value, (dict, list)):
            try:
                json_str = json.dumps(value, ensure_ascii=False)
                if len(json_str) > self.MAX_FIELD_SIZE:
                    return f"[large_object:{type(value).__name__}:{len(json_str)}bytes]"
                return value
            except (TypeError, ValueError):
                return f"[non_serializable:{type(value).__name__}]"

        # Basic types
        if isinstance(value, (int, float, bool)):
            return value

        # Other objects - convert to string
        str_value = str(value)
        if len(str_value) > self.MAX_FIELD_SIZE:
            return str_value[: self.MAX_FIELD_SIZE] + "...[truncated]"
        return str_value

    def _format_exception(self, exc_info) -> Dict[str, str]:
        """Format exception information."""
        exc_type, exc_value, exc_traceback = exc_info

        return {
            "type": exc_type.__name__ if exc_type else "Unknown",
            "message": str(exc_value) if exc_value else "",
            "traceback": self._truncate_traceback(
                traceback.format_exception(exc_type, exc_value, exc_traceback)
            ),
        }

    def _truncate_traceback(self, tb_lines: list) -> str:
        """Truncate traceback size."""
        tb_str = "".join(tb_lines)
        if len(tb_str) > 2000:  # Smaller limit for tracebacks
            return tb_str[:2000] + "\n...[traceback truncated]"
        return tb_str

    def _ensure_size_limit(self, json_str: str, log_entry: Dict[str, Any]) -> str:
        """Ensure JSON size limit."""
        if len(json_str.encode("utf-8")) <= self.MAX_MESSAGE_SIZE:
            return json_str

        # Progressive truncation if size exceeded
        return self._progressive_truncation(log_entry)

    def _progressive_truncation(self, log_entry: Dict[str, Any]) -> str:
        """Simplified truncation strategy - prevents OOM from repeated serialization.

        Note: This method is rarely called now that message is limited to 10KB upfront.

        Stage 1: Shrink long field values
        Stage 2: Batch remove non-core fields (no loop serialization)
        Stage 3: Shrink message (last resort)
        """
        # Stage 1: Shrink long field values
        for key, value in list(log_entry.items()):
            if isinstance(value, str) and len(value) > 500:
                log_entry[key] = value[:500] + "...[truncated]"

        json_str = json.dumps(log_entry, ensure_ascii=False, separators=(",", ":"))
        if len(json_str.encode("utf-8")) <= self.MAX_MESSAGE_SIZE:
            return json_str

        # Stage 2: Batch remove all non-core fields at once (no repeated serialization)
        preserve_keys = set(self.CORE_FIELDS).union(self.CRITICAL_FIELDS)
        keys_to_remove = [k for k in list(log_entry.keys()) if k not in preserve_keys]
        for key in keys_to_remove:
            del log_entry[key]

        json_str = json.dumps(log_entry, ensure_ascii=False, separators=(",", ":"))
        if len(json_str.encode("utf-8")) <= self.MAX_MESSAGE_SIZE:
            return json_str

        # Stage 3: Shrink message (last resort)
        if len(log_entry.get("message", "")) > 200:
            log_entry["message"] = log_entry["message"][:200] + "...[truncated]"

        return json.dumps(log_entry, ensure_ascii=False, separators=(",", ":"))

    def _format_timestamp(self, created: float) -> str:
        """Return an ISO8601 UTC timestamp with trailing Z."""
        timestamp = datetime.fromtimestamp(created, tz=timezone.utc).isoformat()
        return timestamp.replace("+00:00", "Z")

    def _fallback_format(self, record: logging.LogRecord, error: Exception) -> str:
        """Fallback format for when formatting fails."""
        return json.dumps(
            {
                "timestamp": self._format_timestamp(record.created),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
                "formatter_error": str(error),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )


class DatadogJSONFormatter(JSONFormatter):
    """Datadog-optimized JSON formatter with APM trace correlation.

    Extends JSONFormatter with Datadog-specific fields for automatic log-trace
    correlation in Datadog APM. Use this when shipping logs to Datadog.

    Output Format (extends JSONFormatter):
        {
            "timestamp": "2025-10-27T10:00:00.123Z",
            "level": "INFO",
            "status": "info",              # Datadog log level (lowercase)
            "logger": "myapp.module",
            "message": "User action completed",
            "dd.trace_id": "1234567890",   # Datadog trace ID (auto-injected)
            "dd.span_id": "9876543210",    # Datadog span ID (auto-injected)
            "dd_service": "my-service",    # Service name
            "dd_env": "production",        # Environment
            "user_id": "12345"             # Custom fields
        }

    Additional Features (over JSONFormatter):
        - 'status' field: Datadog's standard log level field (lowercase)
        - Preserves dd.trace_id, dd.span_id for APM correlation
        - Preserves dd_service, dd_env tags

    Usage with Datadog APM:
        # Set environment variables
        DD_SERVICE=my-service
        DD_ENV=production
        DD_TRACE_ENABLED=true
        DD_TRACE_LOGS_INJECTION=true

        # Configure logging
        from fastapi_forge.logging import configure_logging
        configure_logging(formatter="datadog")

        # Logs will automatically include trace IDs when using ddtrace-run

    Example:
        import logging
        from fastapi_forge.logging import DatadogJSONFormatter

        handler = logging.StreamHandler()
        handler.setFormatter(DatadogJSONFormatter())
        logger = logging.getLogger(__name__)
        logger.addHandler(handler)

        logger.info("User action", extra={"user_id": "123"})
        # Output includes: status, dd.trace_id, dd.span_id (when using ddtrace)
    """

    # Extend critical fields with Datadog-specific ones
    CRITICAL_FIELDS = {
        "trace_id",
        "dd.trace_id",
        "dd.span_id",
        "dd_service",
        "dd_env",
        "thread_id",
        "component",
    }

    def _build_core_structure(self, record: logging.LogRecord) -> Dict[str, Any]:
        """Build core log structure with Datadog status field."""
        # Parent class already handles caching and message size limiting
        structure = super()._build_core_structure(record)
        structure["status"] = record.levelname.lower()
        return structure

    def _fallback_format(self, record: logging.LogRecord, error: Exception) -> str:
        """Fallback format with Datadog status field."""
        return json.dumps(
            {
                "timestamp": self._format_timestamp(record.created),
                "level": record.levelname,
                "status": record.levelname.lower(),
                "logger": record.name,
                "message": record.getMessage(),
                "formatter_error": str(error),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )


__all__ = ["JSONFormatter", "DatadogJSONFormatter"]
