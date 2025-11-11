# LangChain Integration Guidelines

This guide covers best practices for using fastapi-forge's LangChain utilities to build robust, production-ready LangChain applications.

## Table of Contents

- [Overview](#overview)
- [Installation](#installation)
- [Fallback Utilities](#fallback-utilities)
- [Best Practices](#best-practices)
- [Common Patterns](#common-patterns)
- [Error Handling](#error-handling)
- [Performance Considerations](#performance-considerations)
- [Testing](#testing)

## Overview

The `fastapi_forge.langchain` module provides utilities for building resilient LangChain applications with automatic fallback mechanisms. When a primary chain fails, the system automatically switches to a fallback chain, ensuring your application remains responsive even when errors occur.

### Key Features

- **Automatic Fallback**: Seamlessly switch to backup chains on failure
- **Streaming Support**: Full support for sync/async streaming operations
- **Switch Markers**: Optional markers to notify clients of fallback activation
- **Type Safety**: Fully typed with mypy support
- **Logging**: Built-in logging for debugging and monitoring

## Installation

```bash
# Basic LangChain support
pip install fastapi-forge[langchain]

# With FastAPI integration
pip install fastapi-forge[langchain,fastapi]

# All features
pip install fastapi-forge[all]
```

## Fallback Utilities

### `with_runnable_fallback`

The primary utility for creating robust chains with custom fallback behavior.

```python
from fastapi_forge.langchain import with_runnable_fallback
from langchain_core.runnables import RunnableLambda

# Create chains
primary = RunnableLambda(lambda x: x["value"] * 2)
fallback = RunnableLambda(lambda x: 0)

# Wrap with fallback
chain = with_runnable_fallback(primary, fallback)

# Use it
result = chain.invoke({"value": 5})  # Returns 10
result = chain.invoke({"value": None})  # Returns 0 (fallback)
```

#### Supported Operations

All standard Runnable operations are supported:

```python
# Synchronous invoke
result = chain.invoke(input_data)

# Asynchronous invoke
result = await chain.ainvoke(input_data)

# Synchronous streaming
for chunk in chain.stream(input_data):
    print(chunk)

# Asynchronous streaming
async for chunk in chain.astream(input_data):
    print(chunk)
```

#### Switch Markers

Switch markers allow clients to detect when fallback is activated during streaming:

```python
chain = with_runnable_fallback(
    primary,
    fallback,
    switch_marker={"type": "fallback_activated", "timestamp": time.time()}
)

async for chunk in chain.astream(input_data):
    if isinstance(chunk, dict) and chunk.get("type") == "fallback_activated":
        # Handle fallback notification
        logger.info("Primary chain failed, using fallback")
    else:
        # Process normal output
        process_chunk(chunk)
```

### `with_fallback_dict_chain`

A simpler utility using LangChain's built-in fallback mechanism:

```python
from fastapi_forge.langchain import with_fallback_dict_chain

chain = with_fallback_dict_chain(primary, fallback)
result = chain.invoke(input_data)
```

**When to use**:
- You don't need switch markers
- You don't need custom fallback logic
- You want the simplest implementation

**When to use `with_runnable_fallback` instead**:
- You need switch markers for streaming
- You want more control over fallback behavior
- You need custom logging or monitoring

## Best Practices

### 1. Design Resilient Fallback Chains

Fallback chains should be simpler and more reliable than primary chains:

```python
# ✅ Good: Simple, reliable fallback
primary = complex_llm_chain  # May fail due to API issues
fallback = RunnableLambda(lambda x: "Service temporarily unavailable")

# ❌ Bad: Complex fallback that may also fail
primary = complex_llm_chain
fallback = another_complex_llm_chain  # May also fail!
```

### 2. Use Appropriate Switch Markers

Include useful context in switch markers:

```python
# ✅ Good: Informative marker
switch_marker = {
    "type": "fallback_activated",
    "reason": "primary_timeout",
    "timestamp": time.time()
}

# ❌ Bad: Non-informative marker
switch_marker = True
```

### 3. Log Fallback Events

Fallback activations are automatically logged, but add custom logging for business logic:

```python
class FallbackMetrics:
    def __init__(self):
        self.fallback_count = 0

    def track_fallback(self, reason: str):
        self.fallback_count += 1
        metrics.increment("langchain.fallback", tags=[f"reason:{reason}"])

# Use in your chain
async def monitored_astream(chain, input_data, metrics):
    async for chunk in chain.astream(input_data):
        if isinstance(chunk, dict) and chunk.get("type") == "fallback_activated":
            metrics.track_fallback(chunk.get("reason", "unknown"))
        yield chunk
```

### 4. Handle Configuration

Pass configuration through consistently:

```python
config = RunnableConfig(
    tags=["production", "user-123"],
    metadata={"session_id": "abc123"}
)

# Configuration is passed to both primary and fallback
result = chain.invoke(input_data, config=config)
```

### 5. Test Both Paths

Always test both primary and fallback execution paths:

```python
def test_primary_success():
    chain = with_runnable_fallback(primary, fallback)
    result = chain.invoke(valid_input)
    assert result == expected_primary_result

def test_fallback_triggered():
    chain = with_runnable_fallback(primary, fallback)
    result = chain.invoke(invalid_input)  # Triggers fallback
    assert result == expected_fallback_result
```

## Common Patterns

### Pattern 1: LLM Fallback

Use a cheaper/faster model as fallback:

```python
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic

# Primary: High-quality but may be slow/expensive
primary_llm = ChatAnthropic(model="claude-3-opus-20240229")

# Fallback: Faster, cheaper alternative
fallback_llm = ChatOpenAI(model="gpt-3.5-turbo")

# Create chains
primary_chain = primary_llm | output_parser
fallback_chain = fallback_llm | output_parser

# Wrap with fallback
chain = with_runnable_fallback(
    primary_chain,
    fallback_chain,
    switch_marker={"type": "model_fallback", "to": "gpt-3.5-turbo"}
)
```

### Pattern 2: API Resilience

Fall back to cached responses when APIs fail:

```python
from functools import lru_cache

@lru_cache(maxsize=1000)
def get_cached_response(key: str) -> str:
    return cached_responses.get(key, "Default response")

# Primary: Live API call
primary = RunnableLambda(lambda x: call_external_api(x["query"]))

# Fallback: Cached response
fallback = RunnableLambda(lambda x: get_cached_response(x["query"]))

chain = with_runnable_fallback(primary, fallback)
```

### Pattern 3: Graceful Degradation

Provide reduced functionality when full features fail:

```python
# Primary: Full featured response with formatting
def format_response(data):
    return {
        "answer": generate_detailed_answer(data),
        "sources": find_sources(data),
        "confidence": calculate_confidence(data)
    }

# Fallback: Basic response only
def basic_response(data):
    return {
        "answer": "I encountered an issue. Please try again.",
        "sources": [],
        "confidence": 0.0
    }

primary = RunnableLambda(format_response)
fallback = RunnableLambda(basic_response)

chain = with_runnable_fallback(primary, fallback)
```

### Pattern 4: Multi-Level Fallback

Chain multiple fallback layers:

```python
# Create multiple fallback layers
primary = expensive_accurate_chain
secondary = moderate_chain
tertiary = simple_fallback_chain

# Layer the fallbacks
chain_with_secondary = with_runnable_fallback(primary, secondary)
chain_with_tertiary = with_runnable_fallback(chain_with_secondary, tertiary)

# Now we have: primary → secondary → tertiary
```

## Error Handling

### Exception Handling

All exceptions in primary chains are caught and trigger fallback:

```python
def may_raise_error(data):
    if data["value"] < 0:
        raise ValueError("Negative values not allowed")
    return data["value"] * 2

primary = RunnableLambda(may_raise_error)
fallback = RunnableLambda(lambda x: 0)

chain = with_runnable_fallback(primary, fallback)

# Exception is caught, fallback is used
result = chain.invoke({"value": -5})  # Returns 0
```

### Fallback Chain Errors

If the fallback chain also fails, the exception propagates:

```python
primary = RunnableLambda(lambda x: 1 / x["denominator"])
fallback = RunnableLambda(lambda x: x["missing_key"])  # Will also fail!

chain = with_runnable_fallback(primary, fallback)

try:
    result = chain.invoke({"denominator": 0})
except KeyError:
    # Fallback also failed, exception propagates
    handle_total_failure()
```

**Best Practice**: Ensure fallback chains are highly reliable:

```python
# ✅ Good: Fallback can't fail
fallback = RunnableLambda(lambda x: "Error: Service unavailable")

# ❌ Bad: Fallback may also fail
fallback = RunnableLambda(lambda x: x["required_field"] / 0)
```

### Logging

Fallback activations are automatically logged at WARNING level:

```python
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fastapi_forge.langchain.fallback")

# When fallback is triggered, you'll see:
# WARNING:fastapi_forge.langchain.fallback:[with_runnable_fallback]
#   primary_chain invoke failed, switching to fallback: <error message>
```

Customize logging behavior:

```python
# Adjust log level
logger.setLevel(logging.DEBUG)

# Add custom handler
handler = logging.FileHandler("fallbacks.log")
handler.setFormatter(logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
))
logger.addHandler(handler)
```

## Performance Considerations

### 1. Streaming Overhead

Streaming with fallback has minimal overhead when primary succeeds:

```python
# Benchmark: Primary success (no fallback)
# Overhead: ~1-2% (just try-except wrapper)

# Benchmark: Primary failure (fallback triggered)
# Overhead: Time to detect failure + fallback initialization
```

### 2. Memory Usage

The fallback wrapper maintains references to both chains:

```python
# Memory usage: primary + fallback + small wrapper object
# Typical overhead: < 1KB per chain
```

### 3. Caching

Use caching to improve fallback performance:

```python
from functools import lru_cache

@lru_cache(maxsize=1000)
def cached_fallback_fn(key: str) -> str:
    return compute_fallback_response(key)

fallback = RunnableLambda(lambda x: cached_fallback_fn(x["key"]))
```

### 4. Async Performance

Use async operations for I/O-bound tasks:

```python
# ✅ Good: Async for I/O
async def async_api_call(data):
    async with httpx.AsyncClient() as client:
        response = await client.get(f"/api/{data['id']}")
        return response.json()

primary = RunnableLambda(async_api_call)

# Use with ainvoke/astream
result = await chain.ainvoke(input_data)
```

## Testing

### Unit Tests

Test primary and fallback paths separately:

```python
import pytest
from fastapi_forge.langchain import with_runnable_fallback
from langchain_core.runnables import RunnableLambda

def test_primary_success():
    """Test successful primary execution."""
    primary = RunnableLambda(lambda x: x["value"] * 2)
    fallback = RunnableLambda(lambda x: 0)
    chain = with_runnable_fallback(primary, fallback)

    result = chain.invoke({"value": 5})
    assert result == 10

def test_fallback_triggered():
    """Test fallback activation on primary failure."""
    primary = RunnableLambda(lambda x: 1 / x["denominator"])
    fallback = RunnableLambda(lambda x: -1)
    chain = with_runnable_fallback(primary, fallback)

    result = chain.invoke({"denominator": 0})
    assert result == -1

@pytest.mark.asyncio
async def test_async_streaming_fallback():
    """Test async streaming with fallback."""
    async def primary_stream(x):
        if x["fail"]:
            raise ValueError("Primary failed")
        for i in range(3):
            yield i

    async def fallback_stream(x):
        for i in range(3):
            yield i * 10

    primary = RunnableLambda(primary_stream)
    fallback = RunnableLambda(fallback_stream)
    chain = with_runnable_fallback(
        primary,
        fallback,
        switch_marker={"type": "fallback"}
    )

    chunks = []
    async for chunk in chain.astream({"fail": True}):
        chunks.append(chunk)

    assert {"type": "fallback"} in chunks
    assert 0 in chunks  # From fallback
    assert 10 in chunks  # From fallback
```

### Integration Tests

Test with real LangChain components:

```python
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

@pytest.mark.integration
async def test_llm_fallback():
    """Test fallback between real LLM models."""
    prompt = ChatPromptTemplate.from_template("Answer: {question}")

    # This test requires API keys
    primary_chain = prompt | ChatOpenAI(model="gpt-4")
    fallback_chain = prompt | ChatOpenAI(model="gpt-3.5-turbo")

    chain = with_runnable_fallback(primary_chain, fallback_chain)

    result = await chain.ainvoke({"question": "What is 2+2?"})
    assert "4" in result.content.lower()
```

### Monitoring Tests

Test logging and metrics:

```python
import logging
from io import StringIO

def test_fallback_logging(caplog):
    """Test that fallback activation is logged."""
    primary = RunnableLambda(lambda x: 1 / x["value"])
    fallback = RunnableLambda(lambda x: 0)
    chain = with_runnable_fallback(primary, fallback)

    with caplog.at_level(logging.WARNING):
        result = chain.invoke({"value": 0})

    assert "switching to fallback" in caplog.text
    assert result == 0
```

## Example: Complete FastAPI Integration

Here's a complete example integrating everything:

```python
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.runnables import RunnableLambda
from fastapi_forge.langchain import with_runnable_fallback
import logging

logging.basicConfig(level=logging.INFO)
app = FastAPI()

# Create resilient chain
def create_chain():
    primary = RunnableLambda(lambda x: call_primary_service(x))
    fallback = RunnableLambda(lambda x: call_fallback_service(x))
    return with_runnable_fallback(
        primary,
        fallback,
        switch_marker={"type": "fallback_activated"}
    )

@app.post("/process")
async def process_endpoint(data: dict):
    """Process data with automatic fallback."""
    chain = create_chain()
    result = await chain.ainvoke(data)
    return {"result": result}

@app.post("/stream")
async def stream_endpoint(data: dict):
    """Stream processing with fallback."""
    chain = create_chain()

    async def generate():
        async for chunk in chain.astream(data):
            if isinstance(chunk, dict) and chunk.get("type") == "fallback_activated":
                yield f"data: [FALLBACK]\n\n"
            else:
                yield f"data: {chunk}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
```

## Related Documentation

- [FastAPI Guidelines](./FASTAPI_GUIDELINES.md) - FastAPI best practices
- [Testing Guidelines](./TESTING_GUIDELINES.md) - Testing strategies
- [Performance Monitoring Guide](./PERFORMANCE_MONITORING_GUIDE.md) - Monitoring and tuning

## Additional Resources

- [LangChain Documentation](https://python.langchain.com/)
- [LangChain Runnables Guide](https://python.langchain.com/docs/expression_language/)
- [Example: LangChain Fallback](../examples/04_langchain_fallback/)
