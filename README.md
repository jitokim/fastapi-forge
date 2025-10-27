# FastAPI Forge 🔨

**Production-ready toolkit for FastAPI applications**

FastAPI Forge provides battle-tested patterns and utilities for building production-ready FastAPI applications with minimal boilerplate. Focus on your business logic while we handle the production concerns.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## ✨ Features

- 🪵 **Production Logging**: Generic JSON logging + Datadog-optimized formatter with progressive truncation
- 🔍 **Event Loop Monitoring**: Detect and diagnose blocking operations in async applications
- 🚀 **FastAPI Templates**: Production-ready app templates and best practices
- 🤖 **Langchain Integration**: Utilities for LLM applications (coming soon)
- 📊 **Observability**: Platform-agnostic logging (ELK, Splunk, Grafana) with optional Datadog APM
- ⚙️ **Gunicorn/Uvicorn**: Optimized configurations for production deployment
- 🎯 **Zero Dependencies**: Core logging features require only Python stdlib

## 🚀 Quick Start

### Installation

```bash
# Basic installation (logging only)
pip install fastapi-forge

# With FastAPI
pip install fastapi-forge[fastapi]

# With Gunicorn for production
pip install fastapi-forge[gunicorn]

# With Datadog integration
pip install fastapi-forge[datadog]

# Everything
pip install fastapi-forge[all]
```

### Basic Usage

```python
from fastapi import FastAPI
from fastapi_forge.logging import configure_logging

# Configure generic JSON logging (works with any platform)
configure_logging(formatter="json")

app = FastAPI()

@app.get("/")
def read_root():
    return {"message": "Hello from FastAPI Forge!"}
```

Run with Gunicorn:
```bash
gunicorn main:app \
  -w 4 \
  -k uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000
```

## 📚 Documentation

### Logging

FastAPI Forge provides **two production-ready JSON formatters**:

1. **`JSONFormatter`** (default): Generic formatter compatible with any log aggregation platform
2. **`DatadogJSONFormatter`**: Datadog-optimized with APM trace correlation

#### Key Features

- ✅ **Platform Agnostic**: Works with ELK Stack, Splunk, Grafana Loki, CloudWatch, Datadog, etc.
- ✅ **Progressive Truncation**: 3-stage intelligent size management (Docker 16KB limit)
- ✅ **Handler Isolation**: Separate handlers for Gunicorn ↔ Application logs
- ✅ **Smart Filtering**: Health checks (`/api/_/health`), Langfuse, Langchain, httpx
- ✅ **Exception Formatting**: Structured exception info with traceback truncation
- ✅ **stdout/stderr Separation**: INFO → stdout, WARNING+ → stderr

#### Quick Start - Generic JSON

Works with any log aggregation platform (default):

```python
from fastapi import FastAPI
from fastapi_forge.logging import configure_logging
import logging

# Configure generic JSON logging
configure_logging(formatter="json")  # or just configure_logging()

logger = logging.getLogger(__name__)
app = FastAPI()

@app.get("/")
def root():
    logger.info("Request received", extra={"user_id": "123"})
    return {"status": "ok"}
```

**Output**:
```json
{
  "timestamp": "2025-10-27T10:00:00.123Z",
  "level": "INFO",
  "logger": "__main__",
  "message": "Request received",
  "user_id": "123"
}
```

#### Datadog APM Integration

Use `DatadogJSONFormatter` for automatic log-trace correlation:

```python
# main.py
from dotenv import load_dotenv
load_dotenv()

from fastapi_forge.logging import configure_logging

# Use Datadog-optimized formatter
configure_logging(formatter="datadog")

from fastapi import FastAPI
app = FastAPI()
```

**Environment Variables**:
```bash
# Datadog APM
DD_SERVICE=my-api
DD_ENV=production
DD_TRACE_ENABLED=true
DD_TRACE_LOGS_INJECTION=true  # Critical for trace correlation
DD_PROFILING_ENABLED=true

# Logging
LOG_LEVEL=INFO
```

**Run with ddtrace**:
```bash
ddtrace-run gunicorn main:app \
  -w 4 \
  -k uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000
```

**Output** (with Datadog):
```json
{
  "timestamp": "2025-10-27T10:00:00.123Z",
  "level": "INFO",
  "status": "info",
  "logger": "__main__",
  "message": "Request received",
  "user_id": "123",
  "dd.trace_id": "1234567890123456",
  "dd.span_id": "9876543210",
  "dd_service": "my-api",
  "dd_env": "production"
}
```

#### Advanced Usage

```python
from fastapi_forge.logging import (
    JSONFormatter,
    DatadogJSONFormatter,
    HealthCheckFilter,
    get_logging_config,
)
import logging.config

# Option 1: Get config and customize
config = get_logging_config(formatter="json")
config['root']['level'] = 'DEBUG'
logging.config.dictConfig(config)

# Option 2: Use formatter directly
import logging
handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())  # or DatadogJSONFormatter()
logger = logging.getLogger()
logger.addHandler(handler)
```

### Filters

Built-in filters to reduce log noise:

- **HealthCheckFilter**: Filters `/api/health/heartbeat`, `/api/_/health`
- **LangfuseFilter**: Filters Langfuse library noise
- **LangchainFilter**: Filters Langchain library noise
- **InfoFilter**: Stdout for INFO/DEBUG only
- **WarningAndAboveFilter**: Stderr for WARNING/ERROR/CRITICAL

### Event Loop Monitoring

FastAPI Forge includes an EventLoopMonitor that detects blocking operations in async applications.

#### Why Monitor the Event Loop?

In async Python applications, blocking operations (like `time.sleep()`, synchronous I/O, or CPU-intensive tasks) can freeze the entire event loop, causing:

- Poor performance and unresponsive APIs
- Request timeouts and degraded user experience
- Difficulty diagnosing performance issues

The EventLoopMonitor detects these problems by measuring actual vs expected delay of scheduled `asyncio.sleep()` calls, and captures stack traces to help identify the blocking code.

#### Basic Usage

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi_forge.utils import start_event_loop_monitor, stop_event_loop_monitor

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start monitoring on startup
    monitor = await start_event_loop_monitor(
        check_interval=0.1,      # Check every 100ms
        threshold=0.05,          # Warn if delayed more than 50ms
        capture_stack_trace=True # Capture stack traces on blocking
    )
    yield
    # Stop monitoring on shutdown
    await stop_event_loop_monitor()

app = FastAPI(lifespan=lifespan)
```

#### Configuration

Environment variables:
```bash
EVENT_LOOP_CHECK_INTERVAL=0.1  # Check interval in seconds (default: 0.1)
EVENT_LOOP_THRESHOLD=0.05      # Blocking threshold in seconds (default: 0.05)
EVENT_LOOP_CAPTURE_STACKS=true # Enable stack trace capture (default: true)
```

#### Example Output

When blocking is detected:

```json
{
  "timestamp": "2025-10-27T10:00:00Z",
  "level": "WARNING",
  "logger": "fastapi_forge.utils.blocking_detector",
  "message": "[EVENT_LOOP_BLOCKED] Event loop blocking detected\n\nRunning tasks:\nTask: blocking_endpoint\n  File \"main.py\", line 57, in blocking_endpoint",
  "expected_delay_ms": 100.0,
  "actual_delay_ms": 250.0,
  "excess_delay_ms": 150.0,
  "blocking_ratio": 150.0
}
```

#### Performance Impact

The monitor has minimal overhead:
- Check interval: 100ms (default)
- CPU usage: <0.1% per check
- Memory: ~1-2KB per captured stack trace

#### When to Use

✅ **Use in:**
- Production environments with async workloads
- Debugging performance issues
- Detecting blocking I/O operations
- Monitoring long-running synchronous code

❌ **Skip for:**
- CPU-bound applications (expected blocking)
- Single-threaded synchronous apps

## 📁 Project Structure

```
fastapi-forge/
├── src/fastapi_forge/
│   ├── logging/              # Production logging
│   │   ├── config.py         # Configuration
│   │   ├── formatters.py     # JSONFormatter
│   │   └── filters.py        # Log filters
│   ├── utils/                # Utilities
│   │   └── blocking_detector.py  # Event loop monitoring
│   ├── templates/            # App templates (coming soon)
│   ├── middleware/           # Production middleware (coming soon)
│   └── langchain/            # Langchain utilities (coming soon)
├── examples/
│   ├── 01_basic_fastapi/
│   ├── 02_with_ddtrace/
│   └── 03_with_blocking_monitor/
└── docs/
```

## 🧪 Examples

Check the [`examples/`](./examples/) directory for complete working examples:

- **[01_basic_fastapi](./examples/01_basic_fastapi/)**: Minimal FastAPI app with logging
- **[02_with_ddtrace](./examples/02_with_ddtrace/)**: Production setup with Datadog APM
- **[03_with_blocking_monitor](./examples/03_with_blocking_monitor/)**: Event loop monitoring and blocking detection

## 🤝 Contributing

Contributions are welcome! This is an open-source project.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Built with experience from production FastAPI applications
- Inspired by battle-tested patterns from the Python community
- Datadog integration based on real-world APM requirements

## 🔗 Links

- **Documentation**: [GitHub Wiki](https://github.com/fastapi-forge/fastapi-forge/wiki)
- **Issues**: [GitHub Issues](https://github.com/fastapi-forge/fastapi-forge/issues)
- **PyPI**: [fastapi-forge](https://pypi.org/project/fastapi-forge/) (coming soon)

## 🗺️ Roadmap

- [x] Production logging with Datadog optimization
- [x] JSON formatter with progressive truncation
- [x] Smart log filters (health checks, libraries)
- [x] Event loop monitoring and blocking detection
- [ ] FastAPI app templates
- [ ] Production middleware (correlation ID, error handling)
- [ ] Langchain integration utilities
- [ ] Deployment guides and examples
- [ ] Testing utilities
- [ ] Performance monitoring helpers

---

**Made with ❤️ for the FastAPI community**
