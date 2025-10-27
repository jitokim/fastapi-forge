# Gunicorn + Uvicorn Production Guidelines

> Production deployment guide for FastAPI applications with Gunicorn and Uvicorn workers

This document provides best practices for deploying FastAPI applications in production using Gunicorn as the process manager with Uvicorn workers for async support.

---

## Table of Contents

- [Server Execution Configuration](#server-execution-configuration)
- [Worker Configuration](#worker-configuration)
- [Timeout Settings](#timeout-settings)
- [Worker Recycling](#worker-recycling)
- [Environment Variables](#environment-variables)
- [Datadog Integration](#datadog-integration)
- [Health Checks](#health-checks)
- [Troubleshooting](#troubleshooting)

---

## Server Execution Configuration

### Basic Configuration

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

### With Environment Variables

```bash
ENV WORKERS=4
ENV WORKER_TIMEOUT=180
ENV GRACEFUL_TIMEOUT=120
ENV PORT=8000

gunicorn main:app \
  -w ${WORKERS} \
  -k uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:${PORT} \
  --timeout ${WORKER_TIMEOUT} \
  --graceful-timeout ${GRACEFUL_TIMEOUT} \
  --keep-alive 60 \
  --max-requests 1000 \
  --max-requests-jitter 50
```

### Configuration Parameters Explained

| Parameter | Description | Recommended Value |
|-----------|-------------|-------------------|
| `-w` / `--workers` | Number of worker processes | `2 * CPU cores + 1` (start) |
| `-k` / `--worker-class` | Worker type | `uvicorn.workers.UvicornWorker` (required for async) |
| `--bind` | Socket to bind | `0.0.0.0:8000` |
| `--timeout` | Worker timeout (seconds) | `180` (3 min) for streaming, `60` for regular APIs |
| `--graceful-timeout` | Graceful shutdown timeout | `120` (2 min) |
| `--keep-alive` | HTTP Keep-Alive timeout | `60` (1 min) |
| `--max-requests` | Restart worker after N requests | `1000` (prevent memory leaks) |
| `--max-requests-jitter` | Randomize restart timing | `50` (±50 requests) |

---

## Worker Configuration

### Worker Count Guidelines

**Starting Point**: `2 * CPU cores + 1`

**Example**:
- 2-core CPU: Start with 5 workers
- 4-core CPU: Start with 9 workers
- 8-core CPU: Start with 17 workers

**Tuning Considerations**:

1. **Uvicorn workers handle hundreds of coroutines per worker**
   - One worker can handle 200-500+ concurrent connections
   - Don't need as many workers as traditional sync servers

2. **Monitor these metrics**:
   - CPU usage (should be 60-80% under load)
   - Memory usage per worker (RSS)
   - Request queue length
   - Response time (p50, p95, p99)

3. **Adjust workers based on workload**:
   - **I/O-bound** (most FastAPI apps): Fewer workers (cores ± 2)
   - **CPU-bound** (heavy computation): More workers (2-3x cores)
   - **Mixed workload**: Start with formula, tune based on monitoring

4. **When to increase workers**:
   - ✅ CPU usage consistently low (<50%) but queue is building
   - ✅ Response times increasing under load
   - ✅ Connection pool exhaustion

5. **When to decrease workers**:
   - ✅ High context switching (CPU usage high but throughput low)
   - ✅ Memory pressure (workers consuming too much RAM)
   - ✅ Database/external service connection pool exhaustion

**Example Calculation**:
```python
import multiprocessing

# Conservative approach for async workloads
workers = multiprocessing.cpu_count() + 1

# Or use environment variable
workers = int(os.getenv("WORKERS", multiprocessing.cpu_count() + 1))
```

---

## Timeout Settings

### Worker Timeout (`--timeout`)

**Purpose**: Maximum time a worker can spend on a single request before being killed.

**How it works**: Gunicorn's master process monitors workers. If a worker doesn't send any data for `timeout` seconds, it's killed and restarted.

**Important**: The timeout is based on **inactivity** (no data sent), not total request duration.

**Recommended Values**:

| Application Type | Timeout | Reasoning |
|-----------------|---------|-----------|
| Regular API | 60s | Most requests should complete quickly |
| Long-running tasks | 180s | Background processing, heavy computation |
| **Streaming responses** | 300s+ | **Special case**: Need heartbeat pattern |

### Streaming Timeout Considerations

**Problem**: For streaming responses (SSE, WebSocket-like patterns), if the first chunk is delayed, Gunicorn will kill the worker.

**Solution**: Implement heartbeat pattern (see FASTAPI_GUIDELINES.md "스트리밍 타임아웃 및 Heartbeat" section).

```python
# Send periodic heartbeat chunks to prevent timeout
class HeartbeatStreamer:
    def __init__(self, interval: float = 10.0):
        self.interval = interval

    async def wrap(self, generator: AsyncIterator[bytes]) -> AsyncIterator[bytes]:
        # Implementation in FASTAPI_GUIDELINES.md
        ...
```

### Graceful Timeout (`--graceful-timeout`)

**Purpose**: Time to wait for workers to finish handling requests during shutdown.

**Recommended**: `graceful-timeout` should be less than `timeout`.

**Example**:
- `--timeout 180` (3 min)
- `--graceful-timeout 120` (2 min)

During deployment:
1. Master receives SIGTERM
2. Workers get `graceful-timeout` seconds to finish current requests
3. After timeout, workers are forcefully killed (SIGKILL)

### Keep-Alive Timeout (`--keep-alive`)

**Purpose**: How long to keep idle HTTP connections open for reuse.

**Benefits**:
- Reduces connection overhead for repeated requests
- Improves performance for clients making multiple requests

**Recommended Values**:

| Scenario | Keep-Alive | Reasoning |
|----------|-----------|-----------|
| Public API | 30-60s | Balance between efficiency and resource usage |
| Internal microservices | 60-120s | More aggressive connection reuse |
| High-traffic site | 30s | Prevent resource exhaustion |

**Example**:
```bash
# Internal service with frequent RPCs
--keep-alive 60

# Public API
--keep-alive 30
```

**Trade-offs**:
- ✅ Higher value: Better performance, fewer new connections
- ❌ Higher value: More resources held (memory, file descriptors)

---

## Worker Recycling

### Max Requests (`--max-requests`)

**Purpose**: Restart worker after handling N requests to prevent memory leaks.

**Recommended**: `1000-2000` requests

**Why needed**:
- Prevents gradual memory growth
- Clears accumulated state
- Refreshes worker process

**Example**:
```bash
--max-requests 1000
```

Worker lifecycle:
1. Worker starts
2. Handles up to 1000 requests
3. Worker gracefully shuts down
4. New worker starts immediately

### Max Requests Jitter (`--max-requests-jitter`)

**Purpose**: Randomize the exact restart point to avoid all workers restarting simultaneously.

**Recommended**: `50-100` (5-10% of max-requests)

**Example**:
```bash
--max-requests 1000
--max-requests-jitter 50
```

Actual restart points will be random between:
- Min: 1000 - 50 = 950 requests
- Max: 1000 + 50 = 1050 requests

**Benefits**:
- ✅ Prevents thundering herd
- ✅ Maintains consistent capacity during restarts
- ✅ Smoother load distribution

---

## Environment Variables

### Recommended Environment Variables

```bash
# Worker configuration
WORKERS=4                    # Number of workers
WORKER_TIMEOUT=180          # Request timeout (seconds)
GRACEFUL_TIMEOUT=120        # Graceful shutdown timeout (seconds)
PORT=8000                   # Bind port

# Application settings
LOG_LEVEL=INFO              # Logging level
PYTHONUNBUFFERED=1          # Force unbuffered output

# Optional: Auto-calculate workers
WORKERS=${WEB_CONCURRENCY:-$((2 * $(nproc) + 1))}
```

### Docker Deployment Example

```dockerfile
# Dockerfile
FROM python:3.11-slim

ENV WORKERS=4 \
    WORKER_TIMEOUT=180 \
    GRACEFUL_TIMEOUT=120 \
    PORT=8000 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY . /app

RUN pip install -e ".[gunicorn]"

CMD gunicorn main:app \
    -w ${WORKERS} \
    -k uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:${PORT} \
    --timeout ${WORKER_TIMEOUT} \
    --graceful-timeout ${GRACEFUL_TIMEOUT} \
    --keep-alive 60 \
    --max-requests 1000 \
    --max-requests-jitter 50
```

### Kubernetes Deployment Example

```yaml
# deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: fastapi-app
spec:
  replicas: 3
  template:
    spec:
      containers:
      - name: app
        image: my-fastapi-app:latest
        env:
        - name: WORKERS
          value: "4"
        - name: WORKER_TIMEOUT
          value: "180"
        - name: GRACEFUL_TIMEOUT
          value: "120"
        - name: PORT
          value: "8000"
        ports:
        - containerPort: 8000
        livenessProbe:
          httpGet:
            path: /healthz
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /readyz
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
```

---

## Datadog Integration

### With ddtrace-run

**Purpose**: Automatic instrumentation for Datadog APM and profiling.

```bash
ddtrace-run gunicorn main:app \
  -w 4 \
  -k uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000
```

### Required Environment Variables

```bash
# Datadog configuration
DD_SERVICE=my-api           # Service name
DD_ENV=production           # Environment (dev/staging/production)
DD_VERSION=1.0.0           # App version (optional)
DD_TRACE_ENABLED=true      # Enable tracing
DD_TRACE_LOGS_INJECTION=true  # Inject trace IDs into logs
DD_PROFILING_ENABLED=true  # Enable profiling (optional)

# Datadog Agent
DD_AGENT_HOST=localhost    # Agent host
DD_TRACE_AGENT_PORT=8126   # Trace agent port
```

### Application Code

**Important**: Call `configure_logging()` **after** ddtrace patches logging.

```python
# main.py
from dotenv import load_dotenv
load_dotenv()

# Import logging AFTER ddtrace can patch (when using ddtrace-run)
from fastapi_forge.logging import configure_logging
configure_logging()  # Must be called after ddtrace patches

from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def read_root():
    return {"message": "Hello World"}
```

### Dockerfile with Datadog

```dockerfile
FROM python:3.11-slim

ENV DD_SERVICE=my-api \
    DD_ENV=production \
    DD_TRACE_ENABLED=true \
    DD_TRACE_LOGS_INJECTION=true

WORKDIR /app
COPY . /app

RUN pip install -e ".[datadog,gunicorn]"

CMD ddtrace-run gunicorn main:app \
    -w 4 \
    -k uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:8000
```

---

## Health Checks

### Recommended Endpoints

```python
from fastapi import FastAPI, Response, status

app = FastAPI()

@app.get("/healthz")
def health_check():
    """Liveness probe: Is the service running?"""
    return {"status": "ok"}

@app.get("/readyz")
async def readiness_check():
    """Readiness probe: Is the service ready to accept traffic?"""
    # Check dependencies (DB, cache, external services)
    try:
        # Example: Check database
        # await db.execute("SELECT 1")

        # Example: Check cache
        # await cache.ping()

        return {"status": "ready"}
    except Exception as e:
        return Response(
            content={"status": "not ready", "error": str(e)},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        )
```

### Load Balancer Configuration

**Kubernetes**:
```yaml
livenessProbe:
  httpGet:
    path: /healthz
    port: 8000
  initialDelaySeconds: 30
  periodSeconds: 10
  timeoutSeconds: 5
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /readyz
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 5
  timeoutSeconds: 3
  failureThreshold: 2
```

**Docker Compose**:
```yaml
services:
  api:
    image: my-fastapi-app
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/healthz"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 30s
```

---

## Troubleshooting

### Common Issues

#### 1. Workers Timing Out

**Symptom**: Workers are killed and restarted frequently.

**Causes**:
- Blocking I/O operations in async functions
- Long-running synchronous code
- No heartbeat in streaming responses

**Solutions**:
- ✅ Use async clients for all I/O
- ✅ Offload blocking code with `asyncio.to_thread()`
- ✅ Implement heartbeat for streaming (see FASTAPI_GUIDELINES.md)
- ✅ Monitor event loop blocking (use EventLoopMonitor)
- ✅ Increase timeout if legitimately needed

#### 2. High Memory Usage

**Symptom**: Workers consume excessive memory over time.

**Causes**:
- Memory leaks
- Caching without limits
- Large request/response bodies

**Solutions**:
- ✅ Decrease `--max-requests` to recycle workers more frequently
- ✅ Profile memory usage with `memory_profiler`
- ✅ Implement proper cache eviction
- ✅ Stream large files instead of loading into memory

#### 3. Worker Restart Storm

**Symptom**: All workers restart at once, causing service disruption.

**Causes**:
- Missing or too small `--max-requests-jitter`

**Solutions**:
- ✅ Add `--max-requests-jitter 50` (5-10% of max-requests)
- ✅ Monitor worker restart events in logs

#### 4. Connection Pool Exhaustion

**Symptom**: "Connection pool exhausted" errors.

**Causes**:
- Too many workers for database connection limit
- Not closing connections properly

**Solutions**:
- ✅ Calculate: `workers * connections_per_worker < database_max_connections`
- ✅ Use connection pooling with proper limits
- ✅ Ensure lifespan cleanup closes all connections

**Example**:
```python
# If database allows 100 connections
# And you have 4 workers
# Set pool size to 20 per worker (4 * 20 = 80, leaving 20 for admin)

# Database configuration
DATABASE_POOL_SIZE = 20
DATABASE_MAX_OVERFLOW = 5
```

#### 5. Slow Graceful Shutdown

**Symptom**: Deployments take too long.

**Causes**:
- `graceful-timeout` too high
- Long-running requests not finishing

**Solutions**:
- ✅ Decrease `graceful-timeout` to 30-60s
- ✅ Implement proper cancellation handling
- ✅ Use background tasks for long operations

---

## Quick Reference

### Minimal Configuration

```bash
gunicorn main:app \
  -w 4 \
  -k uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000
```

### Production Configuration

```bash
gunicorn main:app \
  -w 4 \
  -k uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --timeout 180 \
  --graceful-timeout 120 \
  --keep-alive 60 \
  --max-requests 1000 \
  --max-requests-jitter 50 \
  --access-logfile - \
  --error-logfile - \
  --log-level info
```

### With Datadog

```bash
DD_SERVICE=my-api DD_ENV=production DD_TRACE_ENABLED=true \
ddtrace-run gunicorn main:app \
  -w 4 \
  -k uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --timeout 180 \
  --graceful-timeout 120 \
  --keep-alive 60 \
  --max-requests 1000 \
  --max-requests-jitter 50
```

---

## Related Documentation

- [FASTAPI_GUIDELINES.md](./FASTAPI_GUIDELINES.md) - FastAPI development best practices
- [TESTING_GUIDELINES.md](./TESTING_GUIDELINES.md) - Testing patterns and strategies
- [Gunicorn Official Documentation](https://docs.gunicorn.org/en/stable/)
- [Uvicorn Deployment Guide](https://www.uvicorn.org/deployment/)
- [FastAPI Deployment](https://fastapi.tiangolo.com/deployment/)
