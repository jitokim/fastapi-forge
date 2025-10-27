import json
import logging
from datetime import datetime

import pytest

from fastapi_forge.logging import JSONFormatter


def test_json_formatter_generates_utc_timestamp_and_preserves_datadog_fields():
    formatter = JSONFormatter()
    logger = logging.getLogger("test.formatter.utc")

    record = logger.makeRecord(
        name=logger.name,
        level=logging.INFO,
        fn=__file__,
        lno=42,
        msg="test message",
        args=(),
        exc_info=None,
        func=None,
        extra={
            "trace_id": "trace-123",
            "dd.trace_id": "321",
            "dd.span_id": "654",
            "dd_service": "orders",
            "dd_env": "staging",
            "component": "api",
        },
    )

    payload = json.loads(formatter.format(record))

    assert payload["timestamp"].endswith("Z")
    # datetime.fromisoformat requires replacing Z with +00:00
    datetime.fromisoformat(payload["timestamp"].replace("Z", "+00:00"))
    assert payload["dd.trace_id"] == "321"
    assert payload["dd.span_id"] == "654"
    assert payload["dd_service"] == "orders"
    assert payload["dd_env"] == "staging"


@pytest.mark.parametrize("max_size", [200, 400])
def test_progressive_truncation_keeps_critical_fields(max_size: int):
    formatter = JSONFormatter()
    formatter.MAX_MESSAGE_SIZE = max_size

    logger = logging.getLogger("test.formatter.truncation")
    long_value = "x" * 2000

    record = logger.makeRecord(
        name=logger.name,
        level=logging.INFO,
        fn=__file__,
        lno=123,
        msg=long_value,
        args=(),
        exc_info=None,
        func=None,
        extra={
            "payload": long_value,
            "dd.trace_id": "321",
            "dd.span_id": "654",
            "dd_service": "payments",
            "dd_env": "prod",
            "component": "worker",
        },
    )

    payload = json.loads(formatter.format(record))

    assert payload["dd.trace_id"] == "321"
    assert payload["dd.span_id"] == "654"
    assert payload["dd_service"] == "payments"
    assert payload["dd_env"] == "prod"
    assert payload["component"] == "worker"
    assert len(payload["message"]) < len(long_value)
    assert payload["message"].endswith("...[truncated]")
