"""LangChain Fallback Example

This example demonstrates how to use fastapi-forge's LangChain fallback utilities
to create robust chains that gracefully handle failures by switching to fallback chains.

Features demonstrated:
- Basic invoke fallback
- Async invoke fallback
- Streaming with fallback and switch markers
- Integration with FastAPI endpoints
"""

import asyncio
import logging
from typing import Any, Dict

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from langchain_core.runnables import RunnableLambda

from fastapi_forge.langchain import with_runnable_fallback

# Configure logging to see fallback warnings
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="LangChain Fallback Example")


# Example 1: Simple invoke with fallback
def create_simple_chain():
    """Create a simple chain that divides numbers, with a fallback for errors."""

    def divide_operation(data: Dict[str, Any]) -> float:
        """Primary operation that may fail."""
        return data["numerator"] / data["denominator"]

    def safe_fallback(data: Dict[str, Any]) -> str:
        """Fallback that returns a safe error message."""
        return f"Error: Cannot divide {data['numerator']} by {data['denominator']}"

    primary = RunnableLambda(divide_operation)
    fallback = RunnableLambda(safe_fallback)

    return with_runnable_fallback(primary, fallback)


# Example 2: LLM-style streaming with fallback
def create_streaming_chain():
    """Create a streaming chain with fallback and switch marker."""

    async def stream_primary(data: Dict[str, Any]) -> Any:
        """Primary streaming operation."""
        message = data.get("message", "")
        if "error" in message.lower():
            raise ValueError("Primary chain rejected the message")

        # Simulate streaming tokens
        words = f"Primary processed: {message}".split()
        for word in words:
            yield word + " "
            await asyncio.sleep(0.1)

    async def stream_fallback(data: Dict[str, Any]) -> Any:
        """Fallback streaming operation."""
        message = data.get("message", "")
        words = f"Fallback processed: {message}".split()
        for word in words:
            yield word + " "
            await asyncio.sleep(0.1)

    primary = RunnableLambda(stream_primary)
    fallback = RunnableLambda(stream_fallback)

    # Use a switch marker to notify clients when fallback is activated
    switch_marker = {"type": "fallback_activated", "reason": "primary_failed"}

    return with_runnable_fallback(primary, fallback, switch_marker=switch_marker)


# FastAPI Endpoints


@app.get("/")
def read_root():
    """Root endpoint with API information."""
    return {
        "message": "LangChain Fallback Example API",
        "endpoints": {
            "/divide": "POST - Test division with fallback",
            "/stream": "POST - Test streaming with fallback",
            "/health": "GET - Health check",
        },
    }


@app.post("/divide")
def divide_endpoint(numerator: float, denominator: float):
    """Endpoint demonstrating invoke with fallback.

    Try:
    - /divide?numerator=10&denominator=2  -> Returns 5.0
    - /divide?numerator=10&denominator=0  -> Returns error message via fallback
    """
    chain = create_simple_chain()
    result = chain.invoke({"numerator": numerator, "denominator": denominator})
    return {"result": result}


@app.post("/stream")
async def stream_endpoint(message: str):
    """Endpoint demonstrating streaming with fallback.

    Try:
    - /stream?message=Hello world  -> Streams from primary
    - /stream?message=error test   -> Switches to fallback with marker
    """
    chain = create_streaming_chain()

    async def generate():
        async for chunk in chain.astream({"message": message}):
            # Handle switch marker specially
            if isinstance(chunk, dict) and chunk.get("type") == "fallback_activated":
                yield f"data: [FALLBACK ACTIVATED: {chunk.get('reason')}]\n\n"
            else:
                yield f"data: {chunk}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "langchain-fallback-example"}


# Example usage functions for testing


async def example_basic_usage():
    """Demonstrate basic invoke usage."""
    print("\n=== Basic Invoke Example ===")

    chain = create_simple_chain()

    # Successful operation
    result1 = chain.invoke({"numerator": 10, "denominator": 2})
    print(f"10 / 2 = {result1}")

    # Failed operation (triggers fallback)
    result2 = chain.invoke({"numerator": 10, "denominator": 0})
    print(f"10 / 0 = {result2}")


async def example_streaming_usage():
    """Demonstrate streaming usage."""
    print("\n=== Streaming Example ===")

    chain = create_streaming_chain()

    # Successful streaming
    print("\nStreaming 'Hello world':")
    async for chunk in chain.astream({"message": "Hello world"}):
        if isinstance(chunk, dict):
            print(f"[Marker: {chunk}]")
        else:
            print(chunk, end="", flush=True)
    print()

    # Failed streaming (triggers fallback)
    print("\nStreaming 'error test':")
    async for chunk in chain.astream({"message": "error test"}):
        if isinstance(chunk, dict):
            print(f"[Marker: {chunk}]")
        else:
            print(chunk, end="", flush=True)
    print()


async def example_async_invoke():
    """Demonstrate async invoke usage."""
    print("\n=== Async Invoke Example ===")

    def process_data(data: Dict[str, Any]) -> str:
        value = data.get("value", 0)
        if value < 0:
            raise ValueError("Negative values not allowed")
        return f"Processed: {value * 2}"

    def safe_process(data: Dict[str, Any]) -> str:
        return f"Safe fallback for: {data.get('value', 'unknown')}"

    chain = with_runnable_fallback(
        RunnableLambda(process_data), RunnableLambda(safe_process)
    )

    # Successful async operation
    result1 = await chain.ainvoke({"value": 5})
    print(f"Result 1: {result1}")

    # Failed async operation (triggers fallback)
    result2 = await chain.ainvoke({"value": -5})
    print(f"Result 2: {result2}")


async def run_examples():
    """Run all examples."""
    await example_basic_usage()
    await example_streaming_usage()
    await example_async_invoke()


if __name__ == "__main__":
    # Run examples
    print("Running LangChain fallback examples...")
    asyncio.run(run_examples())

    print("\n" + "=" * 60)
    print("To run the FastAPI server:")
    print("  uvicorn main:app --reload")
    print("\nThen try:")
    print("  curl 'http://localhost:8000/divide?numerator=10&denominator=2'")
    print("  curl 'http://localhost:8000/divide?numerator=10&denominator=0'")
    print("  curl -X POST 'http://localhost:8000/stream?message=Hello+world'")
    print("  curl -X POST 'http://localhost:8000/stream?message=error+test'")
    print("=" * 60)
