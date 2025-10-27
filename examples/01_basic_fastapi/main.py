"""Basic FastAPI Example with FastAPI Forge Logging

Minimal example showing how to use FastAPI Forge logging.

## Installation

```bash
pip install fastapi uvicorn fastapi-forge
```

## Run

```bash
# Development (auto-reload)
uvicorn main:app --reload

# Production (with Gunicorn)
pip install gunicorn
gunicorn main:app -w 2 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

## Test

```bash
# Health check (filtered out by HealthCheckFilter)
curl http://localhost:8000/api/_/health

# Root endpoint
curl http://localhost:8000/

# Log levels
curl http://localhost:8000/debug

# Error with exception
curl http://localhost:8000/error
```
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi_forge.logging import configure_logging

# Configure logging
configure_logging()

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    logger.info("Starting FastAPI application")
    yield
    logger.info("Shutting down FastAPI application")


app = FastAPI(
    title="Basic FastAPI with Forge",
    description="Minimal FastAPI application with fastapi-forge logging",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/")
def read_root():
    """Root endpoint"""
    logger.info("Root endpoint called")
    return {
        "message": "Hello from FastAPI Forge!",
        "docs": "/docs",
        "health": "/api/_/health",
    }


@app.get("/api/_/health")
def health_check():
    """Health check endpoint (will be filtered out from logs)"""
    return {"status": "ok"}


@app.get("/debug")
def debug_logs():
    """Test different log levels"""
    logger.debug("This is a DEBUG message")
    logger.info("This is an INFO message")
    logger.warning("This is a WARNING message")
    logger.error("This is an ERROR message")

    return {"message": "Check logs for different levels"}


@app.get("/error")
def trigger_error():
    """Endpoint to test error logging"""
    logger.info("Error endpoint called")
    try:
        result = 1 / 0
    except ZeroDivisionError:
        logger.error(
            "Division by zero occurred",
            exc_info=True,
            extra={"endpoint": "/error"},
        )
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/custom-fields")
def custom_fields():
    """Log with custom fields (extra)"""
    logger.info(
        "Request with custom fields",
        extra={
            "user_id": "12345",
            "action": "custom_request",
            "metadata": {"key": "value"},
        },
    )
    return {"message": "Check logs for custom fields"}


if __name__ == "__main__":
    # For local development
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
