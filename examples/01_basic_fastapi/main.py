"""Example 01: Basic FastAPI with Generic JSON Logging

Demonstrates FastAPI Forge logging with the generic JSONFormatter.
This formatter works with any log aggregation platform (ELK, Splunk, Grafana Loki, etc.)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Installation
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

pip install fastapi uvicorn fastapi-forge

# For production with Gunicorn
pip install gunicorn

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Run
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Development (auto-reload)
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Production (Gunicorn + Uvicorn workers)
gunicorn main:app -w 2 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Test Endpoints
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Health check (filtered - no logs generated)
curl http://localhost:8000/api/_/health

# Root endpoint (generates INFO log)
curl http://localhost:8000/

# Different log levels
curl http://localhost:8000/debug

# Custom fields in logs
curl http://localhost:8000/custom-fields

# Error with exception traceback
curl http://localhost:8000/error

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Expected Log Output (JSON)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{
  "timestamp": "2025-10-27T10:00:00.123Z",
  "level": "INFO",
  "logger": "__main__",
  "message": "Root endpoint called"
}

{
  "timestamp": "2025-10-27T10:00:05.456Z",
  "level": "INFO",
  "logger": "__main__",
  "message": "Request with custom fields",
  "user_id": "12345",
  "action": "custom_request",
  "metadata": {"key": "value"}
}
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi_forge.logging import configure_logging

# Configure logging with generic JSON formatter
# Works with any log aggregation platform (ELK, Splunk, Grafana Loki, etc.)
configure_logging(formatter="json")

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
