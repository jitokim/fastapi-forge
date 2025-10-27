# Example 03: FastAPI with Event Loop Blocking Detection

This example demonstrates how to use the **EventLoopMonitor** to detect blocking operations in your FastAPI application.

## What is Event Loop Blocking?

In async Python applications, blocking operations (like `time.sleep()`, synchronous I/O, or CPU-intensive tasks) can freeze the entire event loop, preventing other tasks from running. This leads to:

- Poor performance
- Unresponsive APIs
- Degraded user experience

The EventLoopMonitor helps you detect and identify these blocking operations.

## How It Works

The monitor runs a background task that periodically schedules an `asyncio.sleep()` and measures how long it actually takes. If the actual delay exceeds the expected delay by more than a threshold, it indicates that the event loop was blocked.

When blocking is detected, the monitor captures stack traces of all running tasks to help you identify the culprit.

## Installation

```bash
pip install fastapi-forge uvicorn
```

## Running the Example

```bash
# Development
uvicorn main:app --reload

# Production
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

## Testing the Endpoints

### Healthy Endpoint (Non-blocking)
```bash
curl http://localhost:8000/healthy
```
This endpoint uses `await asyncio.sleep()` which doesn't block the event loop.

### Semi-Blocking Endpoint
```bash
curl http://localhost:8000/semi-blocking
```
This endpoint uses `time.sleep(0.06)` which blocks for 60ms, exceeding the 50ms threshold. The monitor will log a warning.

### Blocking Endpoint
```bash
curl http://localhost:8000/blocking
```
This endpoint uses `time.sleep(0.2)` which blocks for 200ms. The monitor will log a warning with stack traces showing exactly where the blocking occurred.

## Expected Log Output

When you hit the blocking endpoint, you'll see logs like:

```json
{
  "timestamp": "2025-10-27T10:00:00Z",
  "level": "WARNING",
  "logger": "fastapi_forge.utils.blocking_detector",
  "message": "[EVENT_LOOP_BLOCKED] Event loop blocking detected\n\nRunning tasks:\nTask: Task-5 (blocking_endpoint)\n  File \"/path/to/main.py\", line 57, in blocking_endpoint",
  "expected_delay_ms": 100.0,
  "actual_delay_ms": 250.0,
  "excess_delay_ms": 150.0,
  "blocking_ratio": 150.0
}
```

## Configuration

You can configure the monitor via:

### Code
```python
monitor = await start_event_loop_monitor(
    check_interval=0.1,      # Check every 100ms
    threshold=0.05,          # Warn if delayed more than 50ms
    capture_stack_trace=True # Capture stack traces on blocking
)
```

### Environment Variables
```bash
EVENT_LOOP_CHECK_INTERVAL=0.1
EVENT_LOOP_THRESHOLD=0.05
EVENT_LOOP_CAPTURE_STACKS=true
```

## Best Practices

✅ **DO:**
- Use `await asyncio.sleep()` instead of `time.sleep()`
- Use `asyncio.run_in_executor()` for CPU-bound or blocking operations
- Use async libraries (aiohttp, asyncpg, motor) for I/O
- Monitor production applications to catch unexpected blocking

❌ **DON'T:**
- Use `time.sleep()` in async functions
- Perform synchronous I/O (requests, psycopg2, pymongo)
- Run CPU-intensive loops without yielding to the event loop
- Ignore blocking warnings in production

## Performance Impact

The monitor has minimal overhead:
- Check interval: 100ms (default)
- CPU usage: <0.1% per check
- Memory: ~1-2KB per captured stack trace

## When to Use

✅ **Use in:**
- Production environments with async workloads
- Debugging performance issues
- Detecting blocking I/O operations
- Monitoring long-running synchronous code

❌ **Skip for:**
- CPU-bound applications (expected blocking)
- Single-threaded synchronous apps
