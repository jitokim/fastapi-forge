"""FastAPI Example with Datadog ddtrace Integration

이 예제는 gunicorn_logging_config를 ddtrace와 함께 사용하는 방법을 보여줍니다.

## 실행 방법

### 1. 의존성 설치
```bash
pip install fastapi uvicorn gunicorn ddtrace python-dotenv
```

### 2. 환경 변수 설정 (.env 파일)
```
DD_SERVICE=example-api
DD_ENV=dev
DD_TRACE_ENABLED=true
DD_TRACE_LOGS_INJECTION=true
DD_TRACE_ASYNCIO_ENABLED=true
DD_PROFILING_ENABLED=true
LOG_LEVEL=INFO
```

### 3. Gunicorn으로 실행
```bash
# ddtrace-run 사용 (권장)
ddtrace-run gunicorn example.main:app \
  -w 2 \
  -k uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000

# 또는 로컬 테스트 (ddtrace 없이)
uvicorn example.main:app --reload
```

### 4. 테스트
```bash
# Health check
curl http://localhost:8000/api/_/health

# 일반 요청 (trace context 생성)
curl http://localhost:8000/

# User 생성 (extra 필드 포함)
curl -X POST http://localhost:8000/users -H "Content-Type: application/json" -d '{"name": "Alice"}'

# 에러 테스트
curl http://localhost:8000/error
```

## 로그 출력 예시

ddtrace-run을 사용하면 다음과 같은 로그가 출력됩니다:

```json
{
  "timestamp": "2025-10-27T10:00:00Z",
  "level": "INFO",
  "status": "info",
  "logger": "example.main",
  "message": "User created successfully",
  "user_name": "Alice",
  "dd_trace_id": "1234567890",
  "dd_span_id": "9876543210",
  "dd_service": "example-api",
  "dd_env": "dev"
}
```
"""

import logging
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

# Configure logging after ddtrace patching
configure_logging()

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
