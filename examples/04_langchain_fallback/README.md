# LangChain Fallback Example

This example demonstrates how to use `fastapi-forge`'s LangChain fallback utilities to create robust chains that gracefully handle failures.

## Features

- **Invoke Fallback**: Automatic fallback for synchronous operations
- **Async Invoke Fallback**: Automatic fallback for asynchronous operations
- **Streaming Fallback**: Fallback support for streaming operations with switch markers
- **FastAPI Integration**: Ready-to-use endpoints demonstrating real-world usage

## Installation

```bash
# Install with LangChain support
pip install fastapi-forge[langchain,fastapi]
```

## Quick Start

### Run the Examples

```bash
python main.py
```

This will demonstrate:
1. Basic invoke with fallback for division operations
2. Streaming with fallback and switch markers
3. Async invoke with fallback

### Run the FastAPI Server

```bash
uvicorn main:app --reload
```

Then test the endpoints:

```bash
# Successful division
curl 'http://localhost:8000/divide?numerator=10&denominator=2'
# Returns: {"result": 5.0}

# Division by zero (triggers fallback)
curl 'http://localhost:8000/divide?numerator=10&denominator=0'
# Returns: {"result": "Error: Cannot divide 10 by 0"}

# Successful streaming
curl -X POST 'http://localhost:8000/stream?message=Hello+world'
# Streams from primary chain

# Error in streaming (triggers fallback with marker)
curl -X POST 'http://localhost:8000/stream?message=error+test'
# Streams switch marker, then fallback chain output
```

## Key Concepts

### Basic Fallback

```python
from fastapi_forge.langchain import with_runnable_fallback
from langchain_core.runnables import RunnableLambda

# Create primary and fallback chains
primary = RunnableLambda(lambda x: x["value"] / x["divisor"])
fallback = RunnableLambda(lambda x: 0)  # Safe default

# Wrap with fallback
chain = with_runnable_fallback(primary, fallback)

# Use it
result = chain.invoke({"value": 10, "divisor": 2})  # Returns 5
result = chain.invoke({"value": 10, "divisor": 0})  # Returns 0 (fallback)
```

### Streaming with Switch Markers

```python
# Create a chain with a switch marker
chain = with_runnable_fallback(
    primary_chain,
    fallback_chain,
    switch_marker={"type": "fallback_activated"}
)

# When streaming, the marker is yielded before fallback output
async for chunk in chain.astream(input_data):
    if isinstance(chunk, dict) and chunk.get("type") == "fallback_activated":
        print("Switching to fallback!")
    else:
        print(chunk)
```

## Use Cases

1. **LLM Fallback**: Use a cheaper/faster model when the primary model fails
2. **API Resilience**: Fall back to cached responses when external APIs fail
3. **Graceful Degradation**: Provide basic functionality when advanced features fail
4. **Cost Optimization**: Try expensive operations first, fall back to cheaper alternatives

## API Documentation

See the code comments in `main.py` for detailed function documentation.

## Related Documentation

- [LangChain Guidelines](../../docs/LANGCHAIN_GUIDELINES.md) - Comprehensive guide
- [FastAPI Guidelines](../../docs/FASTAPI_GUIDELINES.md) - FastAPI best practices
