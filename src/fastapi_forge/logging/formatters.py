"""JSON formatters for FastAPI Forge.

Datadog-optimized JSON formatters with progressive truncation and size limits.
"""

import json
import logging
import traceback
from datetime import datetime
from typing import Any, Dict


class JSONFormatter(logging.Formatter):
    """Datadog/ELK/Splunk compatible JSON formatter.

    Features:
    - 3-stage progressive truncation strategy
    - Individual field size limits (MAX_FIELD_SIZE: 1000)
    - Preserve critical fields (trace_id, dd.trace_id, thread_id, component)
    - Enhanced exception formatting with traceback truncation
    - Docker 16KB log size consideration

    Based on lbox-ai-agent's DatadogJSONFormatter with improvements.
    """

    # Core fields - order guaranteed for readability
    CORE_FIELDS = ["timestamp", "level", "logger", "message"]

    # Size limits - considering Docker 16KB limit
    MAX_MESSAGE_SIZE = 15000  # Safety margin included
    MAX_FIELD_SIZE = 1000  # Individual field size limit

    def format(self, record: logging.LogRecord) -> str:
        """Convert log record to Datadog-optimized JSON."""
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
        return {
            "timestamp": datetime.fromtimestamp(record.created).isoformat() + "Z",
            "level": record.levelname,
            "status": record.levelname.lower(),  # Datadog standard field for log level
            "logger": record.name,
            "message": record.getMessage(),
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
        """Progressive truncation - remove/shrink fields by priority.

        Stage 1: Shrink long field values
        Stage 2: Remove non-core fields (preserve critical fields)
        Stage 3: Shrink message
        """
        # Stage 1: Shrink long field values
        for key, value in list(log_entry.items()):
            if isinstance(value, str) and len(value) > 500:
                log_entry[key] = value[:500] + "...[truncated]"

        json_str = json.dumps(log_entry, ensure_ascii=False, separators=(",", ":"))
        if len(json_str.encode("utf-8")) <= self.MAX_MESSAGE_SIZE:
            return json_str

        # Stage 2: Remove non-core fields
        non_core_keys = [k for k in log_entry.keys() if k not in self.CORE_FIELDS]
        for key in non_core_keys:
            # Preserve critical fields
            if key not in ["trace_id", "dd.trace_id", "thread_id", "component"]:
                del log_entry[key]
                json_str = json.dumps(
                    log_entry, ensure_ascii=False, separators=(",", ":")
                )
                if len(json_str.encode("utf-8")) <= self.MAX_MESSAGE_SIZE:
                    return json_str

        # Stage 3: Shrink message
        if len(log_entry.get("message", "")) > 200:
            log_entry["message"] = log_entry["message"][:200] + "...[truncated]"

        return json.dumps(log_entry, ensure_ascii=False, separators=(",", ":"))

    def _fallback_format(self, record: logging.LogRecord, error: Exception) -> str:
        """Fallback format for when formatting fails."""
        return json.dumps(
            {
                "timestamp": datetime.fromtimestamp(record.created).isoformat() + "Z",
                "level": record.levelname,
                "status": record.levelname.lower(),  # Datadog standard field for log level
                "logger": record.name,
                "message": record.getMessage(),
                "formatter_error": str(error),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )


__all__ = ["JSONFormatter"]
