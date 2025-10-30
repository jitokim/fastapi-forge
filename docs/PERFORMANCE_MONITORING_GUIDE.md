# Performance Monitoring & Tuning Guide

Practical guidance on measuring and tuning FastAPI Forge applications with the built-in monitoring tools.

## Table of Contents

1. [Overview](#overview)
2. [EventLoopMonitor - Async Blocking Detection](#eventloopmonitor---async-blocking-detection)
3. [GCMonitor - Garbage Collection Monitoring](#gcmonitor---garbage-collection-monitoring)
4. [Integrated Usage Examples](#integrated-usage-examples)
5. [Performance Measurement Methodology](#performance-measurement-methodology)
6. [Tuning Guide](#tuning-guide)
7. [Troubleshooting](#troubleshooting)
8. [Monitoring Dashboards](#monitoring-dashboards)
9. [References](#references)

---

## Overview

FastAPI Forge ships with two complementary monitoring utilities:

| Tool | Primary Focus | Detects |
|------|---------------|---------|
| **EventLoopMonitor** | Async runtime health | Event loop blocking caused by sync workloads |
| **GCMonitor** | Memory management | GC patterns, memory leaks, suboptimal thresholds |

### Why you need both

Production performance incidents typically fall into two buckets:

1. **CPU or I/O blocking** detected by `EventLoopMonitor`
   - Synchronous I/O (`requests.get()`)
   - CPU heavy work (`time.sleep()`, large loops)
   - Blocking database drivers
2. **Memory exhaustion** detected by `GCMonitor`
   - Aggressive allocations under load
   - Memory leaks, cyclic references
   - Misconfigured garbage collection thresholds

Used together, the monitors pinpoint whether latency or memory is your limiting factor.

---

## EventLoopMonitor - Async Blocking Detection

### Purpose

Python's `asyncio` event loop is single threaded. When any task blocks the loop, the entire application stalls. `EventLoopMonitor` detects these stalls in real time.

### How it works

```python
# core loop
async def _monitor_loop(self):
    while not self._should_stop:
        expected = self.check_interval
        start = time.perf_counter()

        await asyncio.sleep(expected)

        actual = time.perf_counter() - start

        if actual > expected + self.threshold:
            self._log_blocking(expected, actual)
```

If `asyncio.sleep(0.1)` takes significantly longer than 0.1 seconds, something is blocking the loop.

### Basic usage

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi_forge.utils import EventLoopMonitor

@asynccontextmanager
async def lifespan(app: FastAPI):
    monitor = EventLoopMonitor(
        check_interval=0.1,
        threshold=0.05,
        log_excess_only=True,
        capture_stack_trace=True,
    )
    await monitor.start()
    app.state.event_loop_monitor = monitor

    yield

    await monitor.stop()

app = FastAPI(lifespan=lifespan)
```

### Configuration parameters

#### 1. `check_interval`

```python
check_interval=0.1  # seconds
```

Selection guide:
- `0.05`: lowest latency detection (realtime APIs)
- `0.1`: balanced default
- `0.2`: lower overhead for background workloads

#### 2. `threshold`

```python
threshold=0.05  # seconds of tolerated delay
```

Selection guide:
- `0.01`: extremely sensitive, expect noise
- `0.05`: recommended for web APIs
- `0.1`: forgiving for batch workloads

Example:
```
check_interval=0.1, threshold=0.05
- expected: 100 ms sleep
- actual:   160 ms latency
- excess:   60 ms (warning triggered)
```

#### 3. `log_excess_only`

```python
log_excess_only=True   # log only when blocking is detected
log_excess_only=False  # log every cycle (debugging)
```

#### 4. `capture_stack_trace`

```python
capture_stack_trace=True   # record offending stack frames
capture_stack_trace=False  # skip stack capture to reduce overhead
```

### Sample warning log

```json
{
  "timestamp": "2025-10-30T10:00:00Z",
  "level": "WARNING",
  "logger": "fastapi_forge.utils.blocking_detector",
  "message": "[EVENT_LOOP_BLOCKED] Event loop blocking detected\n\nRunning tasks:\nTask: process_payment\n  File \"handlers.py\", line 42, in process_payment\n    result = requests.get(payment_api)",
  "expected_delay_ms": 100.0,
  "actual_delay_ms": 250.0,
  "excess_delay_ms": 150.0,
  "blocking_ratio": 150.0
}
```

### Runtime overhead

```
check_interval = 0.1
- CPU: < 0.1% per check
- Memory: 1-2 KB per captured stack trace
- Throughput: negligible impact
```

---

## GCMonitor - Garbage Collection Monitoring

### Purpose

Python's garbage collector will happily manage memory, but misconfiguration or leaks degrade performance and can trigger OOM kills. `GCMonitor` exposes GC activity so you can act early.

### Generational GC refresher

```
Generation 0: newly allocated objects (most die here)
Generation 1: survivors promoted from gen0
Generation 2: long-lived objects (final cleanup)
```

Default GC thresholds: `(700, 10, 10)`
```
- gen0 collects after 700 allocations
- gen1 collects after 10 gen0 runs
- gen2 collects after 10 gen1 runs
```

### Basic usage

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi_forge.monitoring import GCMonitor

@asynccontextmanager
async def lifespan(app: FastAPI):
    gc_monitor = GCMonitor(
        threshold=(500, 5, 5),
        log_interval=60,
    )
    await gc_monitor.start()
    app.state.gc_monitor = gc_monitor

    yield

    await gc_monitor.stop()

app = FastAPI(lifespan=lifespan)
```

### Configuration parameters

#### 1. `threshold`

```python
# Suggested presets by environment
threshold=(400, 5, 5)   # very constrained, < 500 MB per worker
threshold=(500, 5, 5)   # constrained, 500 MB - 1 GB per worker
threshold=(650, 8, 8)   # balanced, 1 - 2 GB per worker
threshold=(700, 10, 10) # default, ample memory
threshold=None          # keep Python defaults untouched
```

Collection frequency comparison:
```
Threshold (700, 10, 10)
- gen0: every 700 allocations
- gen1: every 7,000 allocations
- gen2: every 70,000 allocations

Threshold (500, 5, 5)
- gen0: every 500 allocations (30% more often)
- gen1: every 2,500 allocations (64% more often)
- gen2: every 12,500 allocations (82% more often)
```

#### 2. `log_interval`

```python
log_interval=60   # every minute (recommended)
log_interval=120  # every two minutes (lower log volume)
log_interval=30   # every 30 seconds (near real-time)
```

### Sample logs

**Worker startup:**
```json
{
  "timestamp": "2025-10-30T10:00:00Z",
  "level": "INFO",
  "message": "GC initial state",
  "worker_pid": 12345,
  "threshold": [700, 10, 10],
  "gen0_collections": 0,
  "gen0_collected": 0,
  "gen0_uncollectable": 0
}
```

**Threshold adjusted:**
```json
{
  "timestamp": "2025-10-30T10:00:01Z",
  "level": "INFO",
  "message": "GC threshold configured",
  "worker_pid": 12345,
  "old_threshold": [700, 10, 10],
  "new_threshold": [500, 5, 5]
}
```

**Periodic snapshot (60 seconds):**
```json
{
  "timestamp": "2025-10-30T10:01:00Z",
  "level": "INFO",
  "message": "GC stats snapshot",
  "worker_pid": 12345,
  "threshold": [500, 5, 5],
  "gen0_collections": 801,
  "gen0_collected": 6128,
  "gen0_uncollectable": 0,
  "gen1_collections": 77,
  "gen1_collected": 1140,
  "gen1_uncollectable": 0,
  "gen2_collections": 6,
  "gen2_collected": 228,
  "gen2_uncollectable": 0
}
```

### Understanding GC stats

| Field | Description | Healthy range | Alert when |
|-------|-------------|---------------|------------|
| `collections` | Number of GC runs | Always increasing | Sudden spikes -> CPU pressure |
| `collected` | Objects reclaimed | Always increasing | Low ratio vs collections |
| `uncollectable` | Objects GC could not free | Exactly zero | Greater than zero indicates leaks |

Key metric:
```python
uncollectable = 0  # healthy
uncollectable > 0  # investigate cyclic references
```

---

## Integrated Usage Examples

### Minimal production setup

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi_forge.utils import EventLoopMonitor
from fastapi_forge.monitoring import GCMonitor

@asynccontextmanager
async def lifespan(app: FastAPI):
    event_loop_monitor = EventLoopMonitor(
        check_interval=0.1,
        threshold=0.05,
        log_excess_only=True,
        capture_stack_trace=True,
    )
    await event_loop_monitor.start()
    app.state.event_loop_monitor = event_loop_monitor

    gc_monitor = GCMonitor(
        threshold=(500, 5, 5),
        log_interval=60,
    )
    await gc_monitor.start()
    app.state.gc_monitor = gc_monitor

    yield

    await gc_monitor.stop()
    await event_loop_monitor.stop()

app = FastAPI(lifespan=lifespan)
```

### Dynamic configuration via environment variables

```python
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi_forge.utils import EventLoopMonitor
from fastapi_forge.monitoring import GCMonitor

@asynccontextmanager
async def lifespan(app: FastAPI):
    env = os.getenv("ENV", "production")
    workers = int(os.getenv("WORKERS", "4"))
    total_memory_gb = float(os.getenv("TOTAL_MEMORY_GB", "2.0"))

    event_loop_monitor = EventLoopMonitor(
        check_interval=float(os.getenv("EVENT_LOOP_CHECK_INTERVAL", "0.1")),
        threshold=float(os.getenv("EVENT_LOOP_THRESHOLD", "0.05")),
        log_excess_only=(env == "production"),
        capture_stack_trace=True,
    )
    await event_loop_monitor.start()

    memory_per_worker = total_memory_gb / workers
    if memory_per_worker < 0.8:
        gc_threshold = (400, 5, 5)
    elif memory_per_worker < 1.2:
        gc_threshold = (500, 5, 5)
    else:
        gc_threshold = (650, 8, 8)

    gc_monitor = GCMonitor(
        threshold=gc_threshold,
        log_interval=int(os.getenv("GC_LOG_INTERVAL", "60")),
    )
    await gc_monitor.start()

    app.state.event_loop_monitor = event_loop_monitor
    app.state.gc_monitor = gc_monitor

    yield

    await gc_monitor.stop()
    await event_loop_monitor.stop()

app = FastAPI(lifespan=lifespan)
```

Example `.env`:
```bash
ENV=production
WORKERS=4
TOTAL_MEMORY_GB=2.0

# Event Loop Monitor
EVENT_LOOP_CHECK_INTERVAL=0.1
EVENT_LOOP_THRESHOLD=0.05

# GC Monitor
GC_LOG_INTERVAL=60
```

---

## Performance Measurement Methodology

### 1. Establish a baseline

Goal: capture healthy steady-state metrics.
```
1. Enable both monitors.
2. Run under normal load for at least 1 hour.
3. Record averages:
   - Event loop: mean delay, max delay, blocking frequency.
   - GC: gen0/1/2 collections, collected counts, uncollectable counts.
```

Sample Datadog queries:
```
# Event loop mean delay
avg:actual_delay_ms by worker_pid

# GC frequency
rate(gen0_collections) by worker_pid
```

### 2. Load testing

Goal: observe behavior as concurrency increases.

Tools: k6, Locust, Apache Bench.

k6 example:
```javascript
import http from 'k6/http';
import { sleep } from 'k6';

export const options = {
  stages: [
    { duration: '1m', target: 10 },
    { duration: '5m', target: 50 },
    { duration: '1m', target: 0 },
  ],
};

export default function () {
  http.get('http://localhost:8000/api/endpoint');
  sleep(1);
}
```

Track during the ramp:
```
- Growth in event loop blocking frequency.
- Growth in GC collections.
- Response time P95 and P99.
- Error rate.
```

### 3. Memory leak testing

Goal: detect leaks during long-lived workloads.
```
1. Enable GCMonitor.
2. Sustain realistic traffic for 8+ hours.
3. Watch uncollectable counts.

Warning signs:
- uncollectable > 0.
- gen2_collected climbs but RSS never drops.
- Memory drops sharply after worker restart.
```

Sample Datadog alert:
```
Alert: @gen1_uncollectable:>0 OR @gen2_uncollectable:>0
Message: "Memory leak detected! Check for circular references"
```

### 4. Event loop blocking analysis

Goal: pinpoint offending code paths.
```
1. Enable capture_stack_trace.
2. Inspect logs when warnings fire.
3. Use stack traces to locate synchronous code.
```

Fix pattern:
```python
# Before (blocking)
result = requests.get(payment_api)

# After (non-blocking)
import httpx
async with httpx.AsyncClient() as client:
    result = await client.get(payment_api)
```

---

## Tuning Guide

### Event loop tuning

#### Issue 1: Frequent blocking warnings

Symptom:
```json
{
  "message": "Event loop blocking detected",
  "excess_delay_ms": 150.0,
  "blocking_ratio": 150.0
}
```

Root cause analysis:
1. Inspect stack trace to locate blocking code.
2. Determine whether it is synchronous I/O or CPU bound work.

Remedies:

**A. Replace synchronous I/O with async clients**
```python
# Before
import requests
response = requests.get(url)

# After
import httpx
async with httpx.AsyncClient() as client:
    response = await client.get(url)
```

**B. Offload CPU heavy work to executors**
```python
# Before
def heavy_computation():
    return sum(range(10_000_000))

result = heavy_computation()

# After
import asyncio
from concurrent.futures import ThreadPoolExecutor

executor = ThreadPoolExecutor()

async def process():
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(executor, heavy_computation)
```

**C. Swap blocking database drivers for async drivers**
```python
# Before (psycopg2)
import psycopg2
conn = psycopg2.connect(...)
cursor = conn.cursor()
cursor.execute("SELECT ...")

# After (asyncpg)
import asyncpg
conn = await asyncpg.connect(...)
rows = await conn.fetch("SELECT ...")
```

#### Issue 2: False positives

Symptom: warnings fire with no real blocking.
Cause: threshold is too aggressive.

Fix:
```python
EventLoopMonitor(
    check_interval=0.1,
    threshold=0.1,
)
```

### GC tuning

#### Issue 1: Out of memory (OOM)

Error pattern:
```bash
[ERROR] Worker (pid:57) was sent SIGKILL! Perhaps out of memory?
```

Diagnosis:
```
1. Review GC stats:
   - uncollectable > 0 -> memory leak.
   - gen2_collections low -> threshold too high.
   - collected/collections ratio low -> objects are retained.

2. Inspect memory trend:
   - Linear growth over time -> leak.
   - Growth proportional to load -> insufficient capacity.
```

Remedies:

**A. Lower thresholds (collect more often)**
```python
# Before
GCMonitor(threshold=(700, 10, 10))

# After
GCMonitor(threshold=(500, 5, 5))
```

**B. Fix leaks (uncollectable > 0)**
```python
# Before (cyclic reference with __del__)
class Node:
    def __init__(self):
        self.ref = None

    def __del__(self):
        print("Deleting")

a = Node()
b = Node()
a.ref = b
b.ref = a  # leak

# After (weakref)
import weakref

class Node:
    def __init__(self):
        self._ref = None

    @property
    def ref(self):
        return self._ref() if self._ref else None

    @ref.setter
    def ref(self, value):
        self._ref = weakref.ref(value) if value else None
```

**C. Rebalance worker count vs memory**
```
2 GB total, 4 workers -> 500 MB per worker (tight)
Option 1: reduce workers (2 GB / 2 = 1 GB per worker)
Option 2: increase memory (4 GB / 4 = 1 GB per worker)
```

#### Issue 2: High CPU from GC

Symptom: CPU spikes, gen0 collections extremely frequent.
Cause: threshold too low.

Fix:
```python
GCMonitor(threshold=(650, 8, 8))
```

#### Issue 3: Persistent leaks (uncollectable > 0)

Diagnosis workflow:

1. Identify cyclic references
```python
import gc

gc.set_debug(gc.DEBUG_SAVEALL)
gc.collect()
for obj in gc.garbage:
    print(type(obj), obj)
```

2. Remove `__del__` when possible
```python
class MyClass:
    def __del__(self):
        pass
```

3. Use `weakref` for parent references
```python
import weakref
self.parent = weakref.ref(parent)
```

---

## Troubleshooting

### Event loop

#### Q1: "Event loop blocking" warnings keep appearing

Checklist:
1. Inspect captured stack traces.
2. Replace synchronous I/O with async clients.
3. Move CPU bound work to executors.
4. Confirm threshold is not below 0.05.

#### Q2: Warnings appear but there is no blocking

Likely cause: transient system load causing jitter.

Fix:
```python
EventLoopMonitor(threshold=0.1)
EventLoopMonitor(log_excess_only=True)
```

#### Q3: Stack traces are missing

Ensure stack capture is enabled:
```python
EventLoopMonitor(capture_stack_trace=True)
```

### Garbage collection

#### Q1: `uncollectable` is greater than zero

Immediate inspection:
```python
import gc
gc.set_debug(gc.DEBUG_SAVEALL)
gc.collect()
print(gc.garbage)
```

Then follow the leak remediation steps outlined above.

#### Q2: `gen2_collections` never increases

Cause: thresholds are too high or objects are not surviving long enough. Lower the thresholds:
```python
GCMonitor(threshold=(500, 5, 5))
```

#### Q3: OOM persists after tuning

Step-by-step checklist:
```
1. uncollectable > 0 -> fix leaks first.
2. gen0_collections low -> thresholds still too high.
3. Memory growth proportional to load -> add capacity or reduce workers.
```

---

## Monitoring Dashboards

### Datadog dashboard blueprint

**Event loop metrics**
```
# Average delay
avg:actual_delay_ms by worker_pid

# Max delay
max:actual_delay_ms by worker_pid

# Blocking frequency
count:excess_delay_ms:>50 by worker_pid

# Blocking ratio
(sum:excess_delay_ms) / (sum:actual_delay_ms) * 100
```

**GC metrics**
```
# GC frequency
rate(gen0_collections) by worker_pid
rate(gen1_collections) by worker_pid
rate(gen2_collections) by worker_pid

# Collection efficiency
gen0_collected / gen0_collections
gen1_collected / gen1_collections
gen2_collected / gen2_collections

# Memory leak indicators
max:gen0_uncollectable by worker_pid
max:gen1_uncollectable by worker_pid
max:gen2_uncollectable by worker_pid
```

**Alert rules**
```
# Event loop blocking
Alert: avg(excess_delay_ms):last_5m > 100
Message: "Event loop blocking detected for 5+ minutes"

# Memory leaks
Alert: max(gen2_uncollectable):last_1m > 0
Message: "Memory leak detected! Uncollectable objects found"

# GC overload
Alert: rate(gen0_collections):last_5m > 100
Message: "Excessive GC activity - check memory usage"
```

---

## References

### Python documentation
- [asyncio - Asynchronous I/O](https://docs.python.org/3/library/asyncio.html)
- [gc - Garbage Collector interface](https://docs.python.org/3/library/gc.html)

### Related tooling
- [Datadog APM](https://docs.datadoghq.com/tracing/)
- [Gunicorn](https://docs.gunicorn.org/)
- [k6 Load Testing](https://k6.io/docs/)

### FastAPI Forge
- [GitHub Repository](https://github.com/jitokim/fastapi-forge)
- [Examples](../examples/)

---

**Document Version**: 1.0
**Last Updated**: 2025-10-30
**Authors**: FastAPI Forge Contributors
