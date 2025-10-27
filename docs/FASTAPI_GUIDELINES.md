# FastAPI Development Guidelines

> Comprehensive best practices for production FastAPI applications

This document provides battle-tested guidelines for building high-performance, production-ready FastAPI applications. These practices are derived from real-world experience and are particularly relevant for applications using:

- FastAPI with async/await patterns
- Gunicorn + Uvicorn workers
- LLM integrations and streaming responses
- High-concurrency scenarios
- Production observability requirements

---

## Table of Contents

- [Server Deployment](#server-deployment)
- [Concurrency & Blocking](#concurrency--blocking)
- [Wrapping Sync SDKs as Async](#wrapping-sync-sdks-as-async)
- [Streaming & Heartbeat](#streaming--heartbeat)
- [Lifecycle & Dependency Injection](#lifecycle--dependency-injection)
- [External HTTP Client Patterns](#external-http-client-patterns)
- [Observability & Logging](#observability--logging)
- [Failure Suppression & Monitoring](#failure-suppression--monitoring)
- [Testing Principles](#testing-principles)
- [Additional Best Practices](#additional-best-practices)

---

## Server Deployment

**📘 For detailed Gunicorn + Uvicorn configuration, see [GUNICORN_GUIDELINES.md](./GUNICORN_GUIDELINES.md).**

**Quick Summary**:
- Use `uvicorn.workers.UvicornWorker` for async FastAPI applications
- Start with `2 * CPU cores + 1` workers, tune based on monitoring
- Set timeouts appropriately: `--timeout 180`, `--graceful-timeout 120`, `--keep-alive 60`
- Enable worker recycling: `--max-requests 1000`, `--max-requests-jitter 50`
- DB connection pools and HTTP client pools: `workers * connections_per_worker < upstream_limit`

**Example**:
```bash
gunicorn main:app \
  -w 4 \
  -k uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --timeout 180 \
  --graceful-timeout 120 \
  --keep-alive 60 \
  --max-requests 1000 \
  --max-requests-jitter 50
```

## Concurrency & Blocking

### Key Principles

1. **Always use async clients in `async def` functions**
   - HTTP: `httpx.AsyncClient` (not `requests`)
   - Database: `asyncpg`, `motor`, `asyncmy` (not sync drivers)
   - Redis: `aioredis` or `redis.asyncio`

2. **Offload blocking operations**
   - Use `asyncio.to_thread()` for simple blocking calls
   - Use dedicated `ThreadPoolExecutor` for frequent blocking operations

3. **Handle failures gracefully**
   - Use `asyncio.gather(..., return_exceptions=True)` for parallel operations
   - One failure shouldn't stop other tasks

4. **Monitor event loop blocking**
   - Detect when sync operations block the event loop
   - FastAPI Forge provides `EventLoopMonitor` for this

### Parallel Execution Pattern

```python
# ✅ Good: Isolated failure handling
tasks = [
    fetch_user_data(user_id),
    fetch_order_history(user_id),
    fetch_recommendations(user_id),
]

results = await asyncio.gather(*tasks, return_exceptions=True)

for result in results:
    if isinstance(result, Exception):
        logger.error("task_failed", error=result)
        # Handle failure (use cached data, default value, etc.)
    else:
        # Process successful result
        ...
```

### Event Loop Monitoring

**💡 FastAPI Forge Tip**: Use the built-in `EventLoopMonitor` from `fastapi_forge.utils` for production-ready event loop monitoring with stack trace capture!

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi_forge.utils import start_event_loop_monitor, stop_event_loop_monitor

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start monitoring on startup
    monitor = await start_event_loop_monitor(
        check_interval=0.1,      # Check every 100ms
        threshold=0.05,          # Warn if delayed >50ms
        capture_stack_trace=True
    )
    yield
    # Stop monitoring on shutdown
    await stop_event_loop_monitor()

app = FastAPI(lifespan=lifespan)
```

---

## Wrapping Sync SDKs as Async

Many external libraries only provide synchronous APIs. Here's how to safely integrate them into async FastAPI applications.

### Principle: Prefer Async Alternatives

| Sync Library | Async Alternative | Status |
|--------------|-------------------|--------|
| `requests` | `httpx.AsyncClient` | ✅ Recommended |
| `boto3` | `aiobotocore` or SDK async client | ✅ Recommended |
| `pymongo` | `motor` | ✅ Recommended |
| `psycopg2` | `asyncpg` or `psycopg3 async` | ✅ Recommended |
| `redis-py` (sync) | `redis.asyncio` | ✅ Recommended |

### When Async Alternative Doesn't Exist

**Option 1: Simple Wrapper with `asyncio.to_thread()` (Python 3.9+)**

For infrequent calls:

```python
from asyncio import to_thread

@app.post("/invoke")
async def invoke_llm(payload: Payload):
    # Simple wrapper for sync SDK
    result = await to_thread(sync_llm_client.invoke, payload.messages)
    return result
```

**⚠️ Limitation**: Can't control thread pool size.

**Option 2: Dedicated ThreadPoolExecutor (Recommended for frequent calls)**

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Optional
from contextlib import asynccontextmanager

class LegacySDKWrapper:
    """Async wrapper for sync SDK with dedicated thread pool."""

    def __init__(self, pool_size: int = 50):
        # Dedicated thread pool (isolated from default)
        self._executor = ThreadPoolExecutor(
            max_workers=pool_size,
            thread_name_prefix="legacy_sdk_"
        )
        self._sync_client = LegacySDK()  # Your sync SDK

    async def query(self, q: str, timeout: float = 5.0) -> dict:
        """Execute sync query asynchronously with timeout."""
        loop = asyncio.get_running_loop()

        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(
                    self._executor,
                    self._sync_client.query,  # Sync function
                    q  # Arguments
                ),
                timeout=timeout
            )
            return result
        except asyncio.TimeoutError:
            raise TimeoutError(f"Query timeout after {timeout}s")

    async def close(self):
        """Cleanup resources (call in lifespan)."""
        self._executor.shutdown(wait=True)


# FastAPI integration
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize wrapper on startup
    sdk_wrapper = LegacySDKWrapper(pool_size=50)
    app.state.legacy_sdk = sdk_wrapper

    yield

    # Cleanup on shutdown
    await sdk_wrapper.close()

app = FastAPI(lifespan=lifespan)

@app.post("/search")
async def search(query: str):
    wrapper = app.state.legacy_sdk
    result = await wrapper.query(query, timeout=10.0)
    return result
```

### Key Considerations

1. **Dedicated ThreadPool Required**
   - ❌ Don't use default pool (`None`): can't control size
   - ✅ Create dedicated pool: better isolation and control

2. **Always Set Timeout**
   - ❌ No timeout: can hang forever
   - ✅ Use `asyncio.wait_for()`: guarantees maximum wait time

3. **Pool Size**
   - Set to 50-100 for frequent calls
   - Must handle concurrent requests without exhaustion

4. **Shutdown Properly**
   - Call `executor.shutdown(wait=True)` in lifespan cleanup
   - Ensures all tasks complete before process exit

### When to Use Which Method

| Situation | Method | Reason |
|-----------|--------|--------|
| Async alternative exists | ✅ Use async library | Best performance & stability |
| No alternative + frequent calls | ✅ Dedicated ThreadPoolExecutor | Control pool size |
| No alternative + rare calls | ✅ `asyncio.to_thread()` | Simplicity |
| Legacy + performance critical | ⚠️ Consider async rewrite | Long-term investment |

---

## Streaming & Heartbeat

### The Timeout Problem

Gunicorn's `--timeout` is based on **inactivity**: if no data is sent for `timeout` seconds, the worker is killed.

**Problem for streaming responses**:
- If the first chunk is delayed (e.g., LLM thinking time), worker gets killed
- Long pauses between chunks also trigger timeout

**Solution**: Send periodic heartbeat chunks to keep the connection alive.

### Heartbeat Implementation

```python
import asyncio
from typing import AsyncIterator

class HeartbeatStreamer:
    """Wrapper that sends periodic heartbeats during streaming."""

    def __init__(self, interval: float = 10.0, message: bytes = b"data: [heartbeat]\n\n"):
        self.interval = interval  # Heartbeat interval in seconds
        self.message = message    # Heartbeat message (SSE format)

    async def wrap(self, generator: AsyncIterator[bytes]) -> AsyncIterator[bytes]:
        """Wrap an async generator with heartbeat support."""
        queue: asyncio.Queue[bytes | None] = asyncio.Queue()

        async def producer() -> None:
            """Read from generator and put chunks in queue."""
            try:
                async for chunk in generator:
                    await queue.put(chunk)
            finally:
                await queue.put(None)  # Sentinel value

        # Start producer task
        asyncio.create_task(producer())

        # Consumer: yield chunks or heartbeats
        while True:
            try:
                # Wait for next chunk with timeout
                chunk = await asyncio.wait_for(queue.get(), timeout=self.interval)
            except asyncio.TimeoutError:
                # No chunk received, send heartbeat
                yield self.message
                continue

            if chunk is None:
                # Stream finished
                break

            yield chunk
```

### FastAPI Integration

```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize heartbeat streamer as singleton
    app.state.heartbeat_streamer = HeartbeatStreamer(interval=10.0)
    yield

app = FastAPI(lifespan=lifespan)

@app.get("/stream")
async def stream_response():
    async def generate():
        # Your streaming logic (e.g., LLM output)
        for i in range(10):
            await asyncio.sleep(2)  # Simulate slow generation
            yield f"data: chunk {i}\n\n".encode()

    # Wrap with heartbeat
    streamer = app.state.heartbeat_streamer
    return StreamingResponse(
        streamer.wrap(generate()),
        media_type="text/event-stream"
    )
```

### Key Points

- **Heartbeat interval**: Set to less than `--timeout` (e.g., timeout=60s → heartbeat=10s)
- **SSE format**: Use `data: [heartbeat]\n\n` for Server-Sent Events
- **Singleton pattern**: Register in `lifespan` for reuse across endpoints
- **Error handling**: Use `try-finally` in producer to ensure sentinel is sent

---

## Lifecycle & Dependency Injection

### Lifespan Pattern

The `lifespan` context manager is the proper way to initialize and cleanup resources in FastAPI.

**Key Principles**:
1. Initialize singleton resources once on startup
2. Every `start()` must have a paired `stop()` or `close()`
3. Store resources in `app.state` for access across the application
4. Use `Depends()` to inject resources into endpoints

### Basic Lifespan Example

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ===== STARTUP =====
    # 1. Configure logging
    from fastapi_forge.logging import configure_logging
    configure_logging()

    # 2. Initialize database connection pool
    db_client = await init_database()
    app.state.db = db_client

    # 3. Initialize HTTP clients
    http_client = httpx.AsyncClient(
        limits=httpx.Limits(max_connections=100),
        timeout=httpx.Timeout(10.0)
    )
    app.state.http_client = http_client

    # 4. Initialize observability tools
    from fastapi_forge.utils import start_event_loop_monitor
    monitor = await start_event_loop_monitor()

    # Application is ready
    yield

    # ===== SHUTDOWN =====
    # Cleanup in reverse order
    from fastapi_forge.utils import stop_event_loop_monitor
    await stop_event_loop_monitor()

    await http_client.aclose()
    await db_client.close()

app = FastAPI(lifespan=lifespan)
```

### Using `app.state` for Dependency Injection

```python
from fastapi import Depends, Request

# Dependency helper functions
def get_db(request: Request):
    return request.app.state.db

def get_http_client(request: Request):
    return request.app.state.http_client

# Use in endpoints
@app.get("/users/{user_id}")
async def get_user(
    user_id: int,
    db=Depends(get_db),
    http_client=Depends(get_http_client)
):
    # Use injected dependencies
    user = await db.fetch_one("SELECT * FROM users WHERE id = $1", user_id)
    return user
```

### Singleton vs Request-Scoped Resources

**Singleton (stored in `app.state`)**:
- ✅ Database connection pools
- ✅ HTTP clients (with connection pooling)
- ✅ Configuration objects
- ✅ Observability clients (OpenTelemetry, Datadog)
- ✅ Caches (Redis client)

**Request-Scoped (created per request)**:
- ✅ Database sessions/transactions
- ✅ Request-specific context (user, trace ID)
- ✅ Temporary data structures

### Example: Request-Scoped Database Session

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def get_db_session(request: Request):
    """Request-scoped database session with transaction."""
    pool = request.app.state.db  # Singleton pool
    async with pool.acquire() as conn:
        async with conn.transaction():
            yield conn
            # Auto-commit on success, rollback on exception

@app.post("/users")
async def create_user(
    user: UserCreate,
    db=Depends(get_db_session)
):
    # Use transactional session
    result = await db.execute(
        "INSERT INTO users (name, email) VALUES ($1, $2) RETURNING id",
        user.name, user.email
    )
    return {"id": result[0]}
```

### Observability Integration

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Configure logging AFTER ddtrace can patch (if using ddtrace-run)
    from fastapi_forge.logging import configure_logging
    configure_logging()

    # Initialize OpenTelemetry/Datadog
    init_opentelemetry(service_name="my-api", env="production")

    yield

    # Flush traces before shutdown
    shutdown_opentelemetry()
```

**💡 FastAPI Forge Tip**: Always call `configure_logging()` in your lifespan after any tracing instrumentation to ensure proper trace ID injection!

---

## External HTTP Client Patterns

Production-ready patterns for external HTTP calls to prevent cascading failures, connection exhaustion, and service degradation.

### 1. Client Instance Management

**Principle**: One dedicated `httpx.AsyncClient` per external service, encapsulated in a service class.

```python
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

class ExternalAPIService:
    """HTTP client wrapper for external API."""

    def __init__(self, base_url: str):
        # Configure connection limits
        limits = httpx.Limits(
            max_connections=100,        # Total concurrent connections
            max_keepalive_connections=20,  # Keep-alive pool size
            keepalive_expiry=60.0       # Keep-alive duration
        )

        # Configure timeouts
        timeout = httpx.Timeout(
            connect=3.0,  # Connection timeout
            read=10.0,    # Read timeout
            write=5.0,    # Write timeout
            pool=3.0      # Pool acquisition timeout
        )

        self._client = httpx.AsyncClient(
            base_url=base_url,
            limits=limits,
            timeout=timeout,
            verify=True  # SSL verification
        )

    @property
    def client(self) -> httpx.AsyncClient:
        return self._client

    async def close(self) -> None:
        """Cleanup: call in lifespan shutdown."""
        if not self._client.is_closed:
            await self._client.aclose()
```

**Integration with Lifespan**:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize HTTP service
    api_service = ExternalAPIService("https://api.example.com")
    app.state.api_service = api_service

    yield

    # Shutdown: cleanup
    await api_service.close()
```

**Key Points**:
- ✅ One client instance per service (singleton)
- ✅ Configured limits prevent connection exhaustion
- ✅ Proper cleanup in lifespan shutdown
- ✅ Can inject same client into SDK if it supports custom transport

### 2. Timeout & Retry Policies

**Timeout Guidelines**:

| Operation | Connect | Read | Total |
|-----------|---------|------|-------|
| Regular API | 2-3s | 5-10s | 15s |
| LLM API | 3s | 30-60s | 90s |
| Internal RPC | 1s | 3s | 5s |

**Retry Pattern with Tenacity**:

```python
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    RetryError
)

class ExternalAPIService:
    # ... (previous code)

    @retry(
        stop=stop_after_attempt(2),  # Max 2 attempts
        wait=wait_exponential(multiplier=0.1, min=0.1, max=0.5),  # Exponential backoff
        retry=retry_if_exception_type(httpx.RequestError),  # Only network errors
        reraise=True  # Re-raise after exhausting retries
    )
    async def fetch_data(self, path: str) -> dict:
        """Fetch data with automatic retry on network errors."""
        try:
            response = await self._client.get(path)
            response.raise_for_status()  # Raise for 4xx/5xx
            return response.json()
        except httpx.HTTPStatusError as e:
            # Don't retry 4xx client errors
            if 400 <= e.response.status_code < 500:
                raise
            # Retry 5xx server errors
            raise
```

**Retry Strategy**:
- ✅ Retry network errors (`RequestError`, `TimeoutException`)
- ✅ Retry 5xx server errors
- ❌ Don't retry 4xx client errors (bad request, auth failure)
- ✅ Short exponential backoff (0.1s → 0.2s → 0.4s)
- ✅ Max 2 attempts total (1 original + 1 retry)

### 3. Failure Detection & Fast Fail

**Circuit Breaker Alternative**: Use health status tracking instead of traditional circuit breakers.

```python
class ServiceHealthRegistry:
    """Track external service health status."""

    def __init__(self):
        self._status: dict[str, bool] = {}

    def mark_healthy(self, service: str):
        self._status[service] = True

    def mark_unhealthy(self, service: str):
        self._status[service] = False

    def is_healthy(self, service: str) -> bool:
        return self._status.get(service, True)  # Default: healthy

# Global registry
health_registry = ServiceHealthRegistry()

class ExternalAPIService:
    def __init__(self, base_url: str, service_name: str):
        self._service_name = service_name
        # ... (previous init code)

    async def fetch_with_health_check(self, path: str) -> dict:
        # Fast fail if service is known to be unhealthy
        if not health_registry.is_healthy(self._service_name):
            raise ServiceUnavailableError(f"{self._service_name} is unhealthy")

        try:
            result = await self.fetch_data(path)
            health_registry.mark_healthy(self._service_name)
            return result
        except Exception as e:
            health_registry.mark_unhealthy(self._service_name)
            logger.error("external_api_failed", service=self._service_name, error=str(e))
            raise
```

### 4. Connection Pool Management

**Fully Async Architecture**:
- Gunicorn + UvicornWorker + async/await + httpx.AsyncClient
- No thread pools needed for I/O (event loop handles concurrency)
- Connection pools naturally limit concurrency

**Connection Pool Configuration**:

```python
limits = httpx.Limits(
    max_connections=100,        # Total connections (across all hosts)
    max_keepalive_connections=20,  # Keep-alive pool
    keepalive_expiry=60.0       # Keep-alive TTL
)
```

**Calculate Pool Size**:
```python
# Rule: total_connections < upstream_limit
# Example: 4 workers, 100 connections each = 400 total
# Ensure upstream service can handle 400 connections

workers = 4
connections_per_worker = 100
total_connections = workers * connections_per_worker  # 400

# Ensure: 400 < upstream_max_connections
```

**No Semaphore Needed**:
- ❌ Don't use `asyncio.Semaphore` to limit concurrent requests
- ✅ Connection pool naturally limits concurrency
- ✅ Maximizes throughput (process requests as fast as possible)
- ✅ Handle rate limits (429) with retry logic

### 5. Failure Isolation with Cache Fallback

```python
import asyncio
from typing import Optional

class ExternalAPIService:
    def __init__(self, base_url: str, cache):
        # ... (previous init code)
        self._cache = cache

    async def search_with_fallback(self, query: str) -> list:
        """Search with cache fallback on failure."""
        cache_key = f"search:{query}"

        try:
            # Try external API
            result = await self.fetch_data(f"/search?q={query}")
            # Update cache on success
            await self._cache.set(cache_key, result, ttl=300)
            return result

        except Exception as e:
            logger.error("external_api_failed", query=query, error=str(e))

            # Try cache fallback
            cached = await self._cache.get(cache_key)
            if cached:
                logger.warning("using_cached_fallback", cache_key=cache_key)
                return cached

            # No cache available, return empty
            return []
```

**Parallel Execution with Isolation**:

```python
async def fetch_multiple_sources(query: str):
    """Fetch from multiple sources, isolated failures."""
    tasks = [
        api_service_1.search_with_fallback(query),
        api_service_2.search_with_fallback(query),
        api_service_3.search_with_fallback(query),
    ]

    # Isolate failures: one failure doesn't stop others
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Filter out failures
    successful_results = [
        r for r in results
        if not isinstance(r, Exception)
    ]

    return successful_results
```

### 6. Error Logging

**Principle**: Log all external API failures at **ERROR** level with structured data.

```python
import structlog

logger = structlog.get_logger()

async def fetch_data(self, path: str):
    try:
        response = await self._client.get(path)
        response.raise_for_status()
        return response.json()

    except httpx.HTTPStatusError as e:
        logger.error(
            "external_api_http_error",
            service=self._service_name,
            path=path,
            status_code=e.response.status_code,
            response_body=e.response.text[:500],  # Truncate
        )
        raise

    except httpx.RequestError as e:
        logger.error(
            "external_api_network_error",
            service=self._service_name,
            path=path,
            error_type=type(e).__name__,
            error=str(e),
        )
        raise
```

**Datadog/OpenTelemetry Integration**:
- ✅ Errors automatically collected by APM
- ✅ Trace spans show which external call failed
- ✅ Structured logs correlate with traces via `dd.trace_id`

### 7. Complete Example

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Request
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

class ExternalAPIService:
    """Production-ready HTTP client for external API."""

    def __init__(self, base_url: str, service_name: str):
        self._service_name = service_name

        limits = httpx.Limits(
            max_connections=100,
            max_keepalive_connections=20,
            keepalive_expiry=60.0
        )
        timeout = httpx.Timeout(connect=3.0, read=10.0, write=5.0, pool=3.0)

        self._client = httpx.AsyncClient(
            base_url=base_url,
            limits=limits,
            timeout=timeout,
            verify=True
        )

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=0.1, min=0.1, max=0.5),
        retry=retry_if_exception_type(httpx.RequestError),
        reraise=True
    )
    async def get(self, path: str) -> dict:
        try:
            response = await self._client.get(path)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error("api_call_failed", service=self._service_name, path=path, error=str(e))
            raise

    async def close(self):
        if not self._client.is_closed:
            await self._client.aclose()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    api_service = ExternalAPIService("https://api.example.com", "example_api")
    app.state.api_service = api_service

    yield

    # Shutdown
    await api_service.close()

app = FastAPI(lifespan=lifespan)

def get_api_service(request: Request) -> ExternalAPIService:
    return request.app.state.api_service

@app.get("/data/{resource_id}")
async def get_data(
    resource_id: str,
    api_service: ExternalAPIService = Depends(get_api_service)
):
    data = await api_service.get(f"/resources/{resource_id}")
    return data
```

### Summary: External HTTP Best Practices

| Goal | Practice |
|------|----------|
| **Stability** | Dedicated `AsyncClient` per service, singleton in lifespan |
| **Performance** | Connection pooling (Limits), keep-alive, no Semaphore |
| **Reliability** | Retry network errors (2 attempts), exponential backoff |
| **Resilience** | Cache fallback, health status tracking, isolated failures |
| **Observability** | Structured error logging, APM integration |
| **Operations** | Timeout on all calls, graceful shutdown (await aclose()) |

---

## Observability & Logging

### Structured Logging

- Standardize server and application logs in JSON format for downstream tools (Datadog, ELK, Splunk)
- Use meaningful span names (e.g., `api-call:search`, `db-query:users`)
- Attach user/session metadata to requests
- Hook `sys.excepthook` and `threading.excepthook` to logging pipeline to catch all exceptions
- Apply logging configuration before worker starts (avoid mixing Gunicorn and application formats)

**💡 FastAPI Forge Features**:
- **JSONFormatter**: Datadog-optimized with progressive truncation (Docker 16KB limit)
- **Smart Filters**: HealthCheckFilter, LangfuseFilter, LangchainFilter
- **Handler Isolation**: Separate Gunicorn ↔ Application logs
- **Datadog APM Integration**: Automatic trace ID injection with `dd.trace_id`

### Example: Structured Logging

```python
from fastapi_forge.logging import configure_logging
import structlog

# Configure in lifespan
configure_logging()

logger = structlog.get_logger()

@app.post("/process")
async def process_data(data: ProcessRequest):
    logger.info(
        "processing_started",
        user_id=data.user_id,
        task_id=data.task_id,
        input_size=len(data.items)
    )

    try:
        result = await process_items(data.items)
        logger.info("processing_completed", task_id=data.task_id, result_count=len(result))
        return result

    except Exception as e:
        logger.error("processing_failed", task_id=data.task_id, error=str(e), exc_info=True)
        raise
```

---

## Failure Suppression & Monitoring

### Preventing Cascading Failures

1. **Rate Limit Handling**
   - Handle upstream 429 (Too Many Requests) with exponential backoff
   - Don't amplify load with aggressive retries
   - Implement cache fallback to reduce upstream pressure

2. **Service Health Registry**
   - Track availability of external services
   - Block requests to known-unhealthy providers
   - Route to healthy alternatives only

3. **Timeout Alignment**
   - Align Gunicorn timeout with API gateway and client timeouts
   - Avoid unnecessary waiting: client timeout < gateway timeout < worker timeout

4. **Health Endpoints**
   - Expose `/healthz` (liveness) and `/readyz` (readiness) endpoints
   - Monitor key metrics: p95 latency, queue depth, worker restart count

### Example: Health Endpoints

```python
from fastapi import FastAPI, Response, status

@app.get("/healthz")
def health_check():
    """Liveness: Is the service running?"""
    return {"status": "ok"}

@app.get("/readyz")
async def readiness_check():
    """Readiness: Is the service ready to accept traffic?"""
    try:
        # Check dependencies
        await db.execute("SELECT 1")
        await cache.ping()
        return {"status": "ready", "dependencies": ["db", "cache"]}
    except Exception as e:
        return Response(
            content={"status": "not ready", "error": str(e)},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        )
```

---

## Testing Principles

**📘 For comprehensive testing guidelines, see [TESTING_GUIDELINES.md](./TESTING_GUIDELINES.md).**

**Quick Summary**:
- Test both success and failure paths for all endpoints
- Use `app.dependency_overrides` to isolate dependencies
- Use `TestClient` (sync) or `AsyncClient` (async) for endpoint testing
- Mock external services and databases
- Keep tests fast and independent (no shared state)

**Example**:

```python
from fastapi.testclient import TestClient

def test_get_user_success():
    # Override dependency
    def mock_db():
        return MockDatabase()

    app.dependency_overrides[get_db] = mock_db

    client = TestClient(app)
    response = client.get("/users/123")

    assert response.status_code == 200
    assert response.json()["id"] == 123

def test_get_user_not_found():
    def mock_db():
        db = MockDatabase()
        db.should_fail = True
        return db

    app.dependency_overrides[get_db] = mock_db

    client = TestClient(app)
    response = client.get("/users/999")

    assert response.status_code == 404
```

---

## Additional Best Practices

### API Design

- Specify `response_model`, `status_code`, and examples in all routes for accurate OpenAPI documentation
- Use clear, RESTful endpoint design
- Separate request/response models (don't reuse the same model)

### Architecture

- Separate module layers: lower layers don't know about upper layers
- Inject configuration via environment variables or secret managers (never hardcode)
- Document middleware order (e.g., CORS → TrustedHost → SecurityHeaders)
- Ensure policy changes propagate quickly

### Security

- Hash passwords with salt (bcrypt, argon2)
- Implement token expiration and refresh strategies
- Never combine `allow_credentials=true` with wildcard CORS origins
- Apply security headers (HSTS, X-Frame-Options, CSP)

### Performance

- Use efficient JSON serialization (orjson, ujson)
- Apply compression (GZip, Brotli) for large responses
- Implement ETag support for conditional requests
- Profile hot paths with profilers

---

## Related Resources

- **[GUNICORN_GUIDELINES.md](./GUNICORN_GUIDELINES.md)**: Production deployment with Gunicorn + Uvicorn
- **[TESTING_GUIDELINES.md](./TESTING_GUIDELINES.md)**: Testing patterns and best practices
- [FastAPI Official Documentation](https://fastapi.tiangolo.com/)
- [Uvicorn Deployment](https://www.uvicorn.org/deployment/)
- [Gunicorn Configuration](https://docs.gunicorn.org/en/stable/configure.html)
- [FastAPI Forge Examples](../examples/)
