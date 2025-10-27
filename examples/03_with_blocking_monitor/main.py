"""Example 03: FastAPI with Event Loop Blocking Detection

Demonstrates FastAPI Forge's EventLoopMonitor for detecting blocking operations.
The monitor automatically logs warnings when the event loop is blocked beyond a threshold.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Installation
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

pip install fastapi uvicorn fastapi-forge

# For production
pip install gunicorn

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Run
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Development
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Production (multiple workers, each with its own monitor)
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Test Endpoints
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Healthy endpoint (no blocking)
curl http://localhost:8000/healthy

# Blocking endpoint (200ms block - will trigger WARNING)
curl http://localhost:8000/blocking

# Semi-blocking endpoint (60ms block - will trigger WARNING with 50ms threshold)
curl http://localhost:8000/semi-blocking

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Expected Behavior
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

When you hit /blocking or /semi-blocking, you'll see WARNING logs like:

{
  "timestamp": "2025-10-27T10:00:00.123Z",
  "level": "WARNING",
  "logger": "fastapi_forge.utils.blocking_monitor",
  "message": "Event loop blocked for 0.2001s",
  "delay_seconds": 0.2001,
  "threshold_seconds": 0.05,
  "check_interval_seconds": 0.1,
  "stack_trace": "..."  # Shows where the blocking occurred
}

This helps identify blocking I/O operations (like time.sleep, requests.get, etc.)
that should be replaced with async equivalents (asyncio.sleep, httpx.get, etc.)
"""

import asyncio
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi_forge.logging import configure_logging
from fastapi_forge.utils import start_event_loop_monitor, stop_event_loop_monitor


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown events."""
    # Configure logging with generic JSON formatter
    configure_logging(formatter="json")

    # Start event loop monitor on application startup
    monitor = await start_event_loop_monitor(
        check_interval=0.1,      # Check every 100ms
        threshold=0.05,          # Warn if delayed more than 50ms
        capture_stack_trace=True # Capture stack traces on blocking
    )

    yield

    # Stop monitoring on application shutdown
    await stop_event_loop_monitor()


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def read_root():
    """Simple endpoint."""
    return {"message": "Hello from FastAPI Forge with blocking detector!"}


@app.get("/healthy")
async def healthy_endpoint():
    """This endpoint is async and non-blocking."""
    await asyncio.sleep(0.01)  # Simulate async I/O
    return {"status": "healthy", "blocking": False}


@app.get("/blocking")
async def blocking_endpoint():
    """This endpoint demonstrates blocking behavior (BAD PRACTICE).

    The monitor will detect this and log a warning with stack traces.
    """
    # This blocks the event loop for 200ms
    time.sleep(0.2)  # BAD: Don't do this in production!
    return {"status": "blocked", "warning": "This endpoint blocked the event loop!"}


@app.get("/semi-blocking")
async def semi_blocking_endpoint():
    """This endpoint demonstrates semi-blocking behavior.

    The monitor might detect this depending on the threshold.
    """
    # This blocks for 60ms, which exceeds our 50ms threshold
    time.sleep(0.06)  # BAD: Don't do this in production!
    return {"status": "semi-blocked", "warning": "This endpoint slightly blocked the event loop!"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
