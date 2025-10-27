# FastAPI Forge 🔨

**Production-ready toolkit for FastAPI applications**

FastAPI Forge provides battle-tested patterns and utilities for building production-ready FastAPI applications with minimal boilerplate. Focus on your business logic while we handle the production concerns.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## ✨ Features

- 🪵 **Production Logging**: Datadog-optimized JSON logging with progressive truncation
- 🚀 **FastAPI Templates**: Production-ready app templates and best practices
- 🤖 **Langchain Integration**: Utilities for LLM applications (coming soon)
- 📊 **Observability**: Built-in support for Datadog APM and logging
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

# Configure production logging
configure_logging()

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

FastAPI Forge provides production-ready logging with:

#### Key Features

- **JSON Format**: Structured logging compatible with Datadog, ELK, Splunk
- **Progressive Truncation**: 3-stage intelligent size management (Docker 16KB limit)
- **Handler Isolation**: Separate handlers for Gunicorn ↔ Application logs
- **Smart Filtering**:
  - Health check endpoints (reduces noise)
  - Langfuse library logs
  - Langchain library logs
- **Critical Field Preservation**: `trace_id`, `dd.trace_id`, `thread_id`, `component`
- **Datadog APM Integration**: Automatic trace ID injection

#### Configuration

```python
from fastapi_forge.logging import configure_logging

# Basic configuration
configure_logging()

# With environment variables
# LOG_LEVEL=DEBUG python main.py
```

#### Datadog APM Integration

```python
# main.py
from dotenv import load_dotenv
load_dotenv()

# Import logging AFTER ddtrace can patch
from fastapi_forge.logging import configure_logging

# This must be called AFTER ddtrace patches logging
configure_logging()

from fastapi import FastAPI
app = FastAPI()
```

Environment variables:
```bash
DD_SERVICE=my-api
DD_ENV=production
DD_TRACE_ENABLED=true
DD_TRACE_LOGS_INJECTION=true  # Inject trace IDs into logs
DD_PROFILING_ENABLED=true
LOG_LEVEL=INFO
```

Run with ddtrace:
```bash
ddtrace-run gunicorn main:app \
  -w 4 \
  -k uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000
```

#### Advanced Usage

```python
from fastapi_forge.logging import (
    JSONFormatter,
    HealthCheckFilter,
    LangfuseFilter,
    get_logging_config,
)
import logging.config

# Get the configuration dict
config = get_logging_config()

# Customize as needed
config['root']['level'] = 'DEBUG'

# Apply configuration
logging.config.dictConfig(config)
```

#### Log Output Example

```json
{
  "timestamp": "2025-10-27T10:00:00Z",
  "level": "INFO",
  "status": "info",
  "logger": "my_app.api",
  "message": "User created successfully",
  "user_id": "12345",
  "action": "create_user",
  "dd_trace_id": "1234567890",
  "dd_span_id": "9876543210",
  "dd_service": "my-api",
  "dd_env": "production"
}
```

### Filters

Built-in filters to reduce log noise:

- **HealthCheckFilter**: Filters `/api/health/heartbeat`, `/api/_/health`
- **LangfuseFilter**: Filters Langfuse library noise
- **LangchainFilter**: Filters Langchain library noise
- **InfoFilter**: Stdout for INFO/DEBUG only
- **WarningAndAboveFilter**: Stderr for WARNING/ERROR/CRITICAL

## 📁 Project Structure

```
fastapi-forge/
├── src/fastapi_forge/
│   ├── logging/           # Production logging
│   │   ├── config.py      # Configuration
│   │   ├── formatters.py  # JSONFormatter
│   │   └── filters.py     # Log filters
│   ├── templates/         # App templates (coming soon)
│   ├── middleware/        # Production middleware (coming soon)
│   ├── langchain/         # Langchain utilities (coming soon)
│   └── utils/             # Utilities
├── examples/
│   ├── 01_basic_fastapi/
│   └── 02_with_ddtrace/
└── docs/
```

## 🧪 Examples

Check the [`examples/`](./examples/) directory for complete working examples:

- **[01_basic_fastapi](./examples/01_basic_fastapi/)**: Minimal FastAPI app with logging
- **[02_with_ddtrace](./examples/02_with_ddtrace/)**: Production setup with Datadog APM

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
- [ ] FastAPI app templates
- [ ] Production middleware (correlation ID, error handling)
- [ ] Langchain integration utilities
- [ ] Deployment guides and examples
- [ ] Testing utilities
- [ ] Performance monitoring helpers

---

**Made with ❤️ for the FastAPI community**
