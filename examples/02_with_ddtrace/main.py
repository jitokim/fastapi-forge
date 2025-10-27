"""Example 02: FastAPI with Datadog APM Integration

Demonstrates FastAPI Forge logging with DatadogJSONFormatter for APM trace correlation.
Logs automatically include dd.trace_id and dd.span_id for linking logs to traces in Datadog.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Installation
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

pip install fastapi uvicorn gunicorn ddtrace python-dotenv

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Environment Variables (.env file)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Datadog APM
DD_SERVICE=example-api
DD_ENV=dev
DD_TRACE_ENABLED=true
DD_TRACE_LOGS_INJECTION=true    # Critical: Inject trace IDs into logs
DD_TRACE_ASYNCIO_ENABLED=true
DD_PROFILING_ENABLED=true

# Logging
LOG_LEVEL=INFO

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Run
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Development with ddtrace (recommended)
cd examples/02_with_ddtrace
ddtrace-run uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Production with Gunicorn + ddtrace
ddtrace-run gunicorn main:app \
  -w 2 \
  -k uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000

# Without ddtrace (for local testing - no trace correlation)
uvicorn main:app --reload

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Test Endpoints
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Health check (filtered - no logs)
curl http://localhost:8000/api/_/health

# Root endpoint (generates trace)
curl http://localhost:8000/

# Create user (with custom fields)
curl -X POST http://localhost:8000/users \
  -H "Content-Type: application/json" \
  -d '{"name": "Alice"}'

# Get user
curl http://localhost:8000/users/1

# Error with exception
curl http://localhost:8000/error

# Different log levels
curl http://localhost:8000/debug

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Expected Log Output (with ddtrace-run)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{
  "timestamp": "2025-10-27T10:00:00.123Z",
  "level": "INFO",
  "status": "info",                    # Datadog standard field
  "logger": "__main__",
  "message": "User created successfully",
  "user_id": 1,
  "user_name": "Alice",
  "action": "create_user",
  "dd.trace_id": "1234567890123456",   # Datadog trace ID (auto-injected)
  "dd.span_id": "9876543210",          # Datadog span ID (auto-injected)
  "dd_service": "example-api",         # From DD_SERVICE
  "dd_env": "dev"                      # From DD_ENV
}

Note: dd.trace_id and dd.span_id are automatically injected by ddtrace when
      DD_TRACE_LOGS_INJECTION=true. Click trace IDs in Datadog to see logs!
"""

import logging
import os
from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# IMPORTANT: Configure logging AFTER ddtrace patching
# This ensures DD_TRACE_LOGS_INJECTION works correctly
from fastapi_forge.logging import configure_logging

# Configure logging with Datadog-optimized formatter
configure_logging(formatter="datadog")

logger = logging.getLogger(__name__)


# Request/Response models
class User(BaseModel):
    name: str


class UserResponse(BaseModel):
    id: int
    name: str
    message: str


# In-memory storage
users_db: Dict[int, str] = {}
user_id_counter = 0


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    logger.info("Starting Example API with ddtrace integration")
    logger.info(
        "Datadog configuration",
        extra={
            "dd_service": os.getenv("DD_SERVICE", "unknown"),
            "dd_env": os.getenv("DD_ENV", "unknown"),
            "trace_injection": os.getenv("DD_TRACE_LOGS_INJECTION", "false"),
        },
    )
    yield
    logger.info("Shutting down Example API")


# Create FastAPI application
app = FastAPI(
    title="Example API with ddtrace",
    description="Example FastAPI application with gunicorn_logging_config and ddtrace",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/")
def read_root() -> Dict[str, Any]:
    """Root endpoint with INFO log"""
    logger.info("Root endpoint called")
    return {
        "message": "Hello World",
        "docs": "/docs",
        "health": "/api/_/health",
    }


@app.get("/api/_/health")
def health_check() -> Dict[str, str]:
    """Health check endpoint (minimal logging)"""
    return {"status": "ok"}


@app.post("/users", response_model=UserResponse)
def create_user(user: User) -> UserResponse:
    """Create a new user with extra logging fields"""
    global user_id_counter
    user_id_counter += 1

    users_db[user_id_counter] = user.name

    # Log with extra fields
    logger.info(
        "User created successfully",
        extra={
            "user_id": user_id_counter,
            "user_name": user.name,
            "action": "create_user",
        },
    )

    return UserResponse(
        id=user_id_counter,
        name=user.name,
        message=f"User {user.name} created with ID {user_id_counter}",
    )


@app.get("/users/{user_id}", response_model=UserResponse)
def get_user(user_id: int) -> UserResponse:
    """Get a user by ID"""
    if user_id not in users_db:
        logger.warning(
            "User not found",
            extra={
                "user_id": user_id,
                "action": "get_user",
            },
        )
        raise HTTPException(status_code=404, detail="User not found")

    user_name = users_db[user_id]
    logger.info(
        "User retrieved",
        extra={
            "user_id": user_id,
            "user_name": user_name,
            "action": "get_user",
        },
    )

    return UserResponse(
        id=user_id,
        name=user_name,
        message=f"User {user_name} with ID {user_id}",
    )


@app.get("/error")
def trigger_error():
    """Endpoint to test error logging with exception info"""
    logger.info("Error endpoint called")
    try:
        # Intentional error
        result = 1 / 0
    except ZeroDivisionError as e:
        logger.error(
            "Division by zero occurred",
            exc_info=True,
            extra={
                "action": "trigger_error",
                "error_type": "ZeroDivisionError",
            },
        )
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/debug")
def debug_logs():
    """Endpoint to test different log levels"""
    logger.debug("This is a DEBUG message")
    logger.info("This is an INFO message")
    logger.warning("This is a WARNING message")
    logger.error("This is an ERROR message")

    return {"message": "Check logs for different levels"}


if __name__ == "__main__":
    # For local development without ddtrace
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
