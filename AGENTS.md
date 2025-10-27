# FastAPI Forge - Agent Development Guide

> Quick reference for AI agents working on FastAPI Forge

## Project Overview

**FastAPI Forge** is a production-ready toolkit for building FastAPI applications with battle-tested patterns. The project provides:

- 🪵 Production logging (Datadog-optimized JSON with progressive truncation)
- 🔍 Event loop monitoring (detect blocking operations)
- 🚀 FastAPI templates and best practices
- 📊 Built-in observability (Datadog APM, structured logging)
- ⚙️ Zero-dependency core (stdlib only for logging)

**Target Users**: Python developers building production FastAPI applications, especially with async/streaming workloads and LLM integrations.

**License**: MIT

---

## Project Structure

```
fastapi-forge/
├── src/fastapi_forge/           # Main package
│   ├── __init__.py
│   ├── logging/                 # Production logging module
│   │   ├── __init__.py          # Public API: configure_logging()
│   │   ├── config.py            # get_logging_config(), dictConfig wrapper
│   │   ├── formatters.py        # JSONFormatter with progressive truncation
│   │   └── filters.py           # HealthCheckFilter, LangfuseFilter, etc.
│   ├── utils/                   # Utility modules
│   │   ├── __init__.py          # Public API: EventLoopMonitor, start/stop_event_loop_monitor
│   │   └── blocking_detector.py # Event loop monitoring
│   ├── templates/               # (Future) FastAPI app templates
│   ├── middleware/              # (Future) Production middleware
│   └── langchain/               # (Future) LangChain utilities
├── examples/                    # Working examples
│   ├── 01_basic_fastapi/        # Minimal FastAPI + logging
│   ├── 02_with_ddtrace/         # Production with Datadog APM
│   └── 03_with_blocking_monitor/# Event loop monitoring
├── docs/                        # Documentation
│   └── FASTAPI_GUIDELINES.md    # Detailed FastAPI best practices
├── pyproject.toml               # Modern Python packaging (PEP 518)
├── README.md                    # User-facing documentation
└── AGENTS.md                    # This file (AI agent guide)
```

---

## Architecture & Design Principles

### Module Organization

1. **Modular Design**: Each feature is isolated in its own submodule with clear public API
   - `logging/`: Filters, formatters, config separated
   - `utils/`: Independent utility modules

2. **Zero Core Dependencies**: Core logging requires only Python stdlib
   - Optional dependencies: `fastapi`, `gunicorn`, `ddtrace` via `[fastapi]`, `[gunicorn]`, `[datadog]` extras

3. **Production First**: All features are battle-tested for production use
   - JSON logging with Docker 16KB limit consideration
   - Progressive truncation to prevent log loss
   - Handler isolation (Gunicorn ↔ Application)

### Key Concepts

#### Logging Architecture

**Problem Solved**: Production FastAPI apps need structured JSON logging that:
- Works with Datadog/ELK/Splunk
- Respects Docker log size limits (16KB)
- Integrates with Datadog APM (trace injection)
- Filters noisy library logs (Langfuse, Langchain)
- Separates Gunicorn server logs from application logs

**Implementation**:
```python
# src/fastapi_forge/logging/formatters.py
class JSONFormatter:
    MAX_MESSAGE_SIZE = 15000  # Docker 16KB limit
    MAX_FIELD_SIZE = 1000

    def _progressive_truncation(self, log_entry):
        # Stage 1: Shrink long fields
        # Stage 2: Remove non-core (preserve trace_id, dd.trace_id, thread_id, component)
        # Stage 3: Shrink message if still too large
```

**Handler Isolation**:
- `root_stdout`/`root_stderr`: Application logs (with Langfuse/Langchain filters)
- `gunicorn_stdout`/`gunicorn_stderr`: Server logs (with HealthCheckFilter)

#### Event Loop Monitoring

**Problem Solved**: Async FastAPI apps can have blocking operations (`time.sleep()`, sync I/O) that freeze the event loop, causing timeouts and poor performance.

**Implementation**:
```python
# src/fastapi_forge/utils/blocking_detector.py
class EventLoopMonitor:
    async def _monitor_loop(self):
        start_time = time.perf_counter()
        await asyncio.sleep(self.check_interval)
        actual_delay = time.perf_counter() - start_time
        excess_delay = actual_delay - self.check_interval

        if excess_delay > self.threshold:
            # Log warning + capture stack traces of running tasks
```

**Configuration**:
- Environment variables: `EVENT_LOOP_CHECK_INTERVAL`, `EVENT_LOOP_THRESHOLD`, `EVENT_LOOP_CAPTURE_STACKS`
- Minimal overhead: <0.1% CPU, ~1-2KB per stack trace

---

## Development Guidelines

### FastAPI Best Practices

**⚠️ IMPORTANT**: For detailed FastAPI development guidelines, see:
- **[docs/FASTAPI_GUIDELINES.md](./docs/FASTAPI_GUIDELINES.md)**

This document covers:
- Server execution (Gunicorn + Uvicorn workers)
- Worker and performance tuning
- Concurrency and blocking handling
- Streaming timeouts and heartbeat
- Lifecycle and dependency injection
- External HTTP guardrails
- Observability and logging
- Failure suppression and monitoring
- Testing principles

**Key Principles (Summary)**:
1. **Use async clients**: Always use `httpx.AsyncClient`, `asyncpg`, `motor` for I/O
2. **Offload blocking**: Wrap sync functions with `asyncio.to_thread()`
3. **Monitor event loop**: Use `EventLoopMonitor` to detect blocking
4. **Structured logging**: Use JSON formatter with Datadog integration
5. **Lifecycle management**: Initialize resources in `lifespan`, clean up on shutdown
6. **Test isolation**: Use `app.dependency_overrides` for testing

### Code Style

- **Type hints**: All functions must have type hints
- **Docstrings**: Public APIs require comprehensive docstrings with examples
- **Async/await**: Prefer `async def` for I/O-bound operations
- **Naming**:
  - Classes: `PascalCase`
  - Functions: `snake_case`
  - Constants: `UPPER_SNAKE_CASE`
  - Private: `_leading_underscore`

### Adding New Features

**Checklist**:
1. [ ] Create module in appropriate subdirectory (`logging/`, `utils/`, `middleware/`, etc.)
2. [ ] Add comprehensive docstrings with usage examples
3. [ ] Export public API in `__init__.py`
4. [ ] Create example in `examples/` directory
5. [ ] Update main `README.md` with feature description
6. [ ] Add to roadmap (mark as completed)
7. [ ] Update `pyproject.toml` if new dependencies added
8. [ ] Commit with descriptive message (see Git Conventions)

**Example PR Flow**:
```
feat: add middleware for correlation ID injection

- Add CorrelationIDMiddleware in src/fastapi_forge/middleware/
- Middleware injects X-Correlation-ID header for request tracing
- Add example 04_with_correlation_id
- Update README with middleware section
- Add CORRELATION_ID_HEADER env var support
```

### Git Conventions

**Commit Message Format**:
```
<type>: <short description>

- <detailed change 1>
- <detailed change 2>

🤖 Generated with [Claude Code](https://claude.ai/code)

Co-Authored-By: Claude <noreply@anthropic.com>
```

**Types**: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`

---

## Working with Existing Code

### Logging Module (`src/fastapi_forge/logging/`)

**Entry Point**: `configure_logging()` in `config.py`
- Call this function to set up production logging
- Must be called AFTER `ddtrace` patches logging (if using Datadog)

**Key Files**:
- `formatters.py`: JSONFormatter with progressive truncation logic
- `filters.py`: 5 filter classes (InfoFilter, WarningAndAboveFilter, HealthCheckFilter, LangfuseFilter, LangchainFilter)
- `config.py`: `get_logging_config()` returns dictConfig, `configure_logging()` applies it

**Critical Fields** (never truncated):
- `trace_id`: OpenTelemetry trace ID
- `dd.trace_id`: Datadog trace ID (injected by ddtrace)
- `thread_id`: Thread identifier
- `component`: Component name

**Truncation Strategy**:
1. Shrink long fields (>500 chars) to 500 + "...[truncated]"
2. Remove non-core fields (keep core + critical fields)
3. Shrink message if still too large

### Utils Module (`src/fastapi_forge/utils/`)

**Entry Point**: `start_event_loop_monitor()` convenience function

**Key Files**:
- `blocking_detector.py`: EventLoopMonitor class + convenience functions
- `__init__.py`: Exports EventLoopMonitor, start_event_loop_monitor, stop_event_loop_monitor

**Usage Pattern**:
```python
from fastapi_forge.utils import start_event_loop_monitor, stop_event_loop_monitor

@asynccontextmanager
async def lifespan(app: FastAPI):
    monitor = await start_event_loop_monitor()
    yield
    await stop_event_loop_monitor()
```

---

## Testing

**Test Structure** (Future):
```
tests/
├── unit/
│   ├── logging/
│   │   ├── test_formatters.py
│   │   └── test_filters.py
│   └── utils/
│       └── test_blocking_detector.py
└── integration/
    └── test_fastapi_app.py
```

**Testing Principles**:
- Unit tests for formatters, filters, utilities
- Integration tests with TestClient/AsyncClient
- Use `app.dependency_overrides` for dependency injection
- Mock external services (Datadog, HTTP clients)

---

## Common Tasks

### Adding a New Filter

1. Add filter class to `src/fastapi_forge/logging/filters.py`:
```python
class MyCustomFilter(logging.Filter):
    """Filter description."""
    def filter(self, record: logging.LogRecord) -> bool:
        # Filter logic
        return True
```

2. Register in `src/fastapi_forge/logging/config.py`:
```python
"filters": {
    "my_custom": {"()": MyCustomFilter},
}
```

3. Apply to handlers:
```python
"handlers": {
    "root_stdout": {
        "filters": ["info_only", "my_custom"],
    }
}
```

4. Export in `src/fastapi_forge/logging/__init__.py`:
```python
from .filters import MyCustomFilter

__all__ = [..., "MyCustomFilter"]
```

### Creating a New Example

1. Create directory: `examples/XX_my_example/`
2. Add files:
   - `main.py`: Working FastAPI app
   - `README.md`: Usage instructions
   - `requirements.txt`: Dependencies
3. Update main `README.md`:
```markdown
- **[XX_my_example](./examples/XX_my_example/)**: Description
```

### Updating Dependencies

1. Edit `pyproject.toml`:
```toml
[project.optional-dependencies]
my_feature = ["new-dependency>=1.0.0"]
```

2. Test installation:
```bash
pip install -e ".[my_feature]"
```

---

## FAQs for Agents

**Q: Where should I add a new utility function?**
A: If it's general-purpose (not FastAPI-specific), add to `src/fastapi_forge/utils/`. If it's FastAPI-specific, consider `middleware/` or `templates/`.

**Q: How do I test Datadog integration without Datadog?**
A: Mock `ddtrace` patching and check that `dd.trace_id` field is preserved in logs.

**Q: Should I modify existing formatters or create new ones?**
A: Modify `JSONFormatter` for general improvements. Create new formatters only if fundamentally different behavior is needed (e.g., plain text formatter).

**Q: Where do I document new features?**
A: Update `README.md` (user-facing) and this `AGENTS.md` (AI-facing). Add detailed docs to `docs/` if needed.

**Q: How do I handle breaking changes?**
A: Follow semantic versioning. Deprecate old APIs before removing (add warnings). Document migration path in release notes.

---

## Quick Reference

**Import Patterns**:
```python
# Logging
from fastapi_forge.logging import configure_logging, JSONFormatter, HealthCheckFilter

# Utils
from fastapi_forge.utils import EventLoopMonitor, start_event_loop_monitor

# Future modules
from fastapi_forge.middleware import ...
from fastapi_forge.templates import ...
```

**Environment Variables**:
```bash
# Logging
LOG_LEVEL=INFO

# Event Loop Monitoring
EVENT_LOOP_CHECK_INTERVAL=0.1
EVENT_LOOP_THRESHOLD=0.05
EVENT_LOOP_CAPTURE_STACKS=true

# Datadog APM
DD_SERVICE=my-api
DD_ENV=production
DD_TRACE_ENABLED=true
DD_TRACE_LOGS_INJECTION=true
```

**Useful Commands**:
```bash
# Install for development
pip install -e ".[all]"

# Run example
cd examples/01_basic_fastapi
uvicorn main:app --reload

# Format code (future)
ruff format .

# Type check (future)
mypy src/
```

---

## Related Documentation

- **[README.md](./README.md)**: User-facing documentation
- **[docs/FASTAPI_GUIDELINES.md](./docs/FASTAPI_GUIDELINES.md)**: Detailed FastAPI best practices
- **[LICENSE](./LICENSE)**: MIT License
- **[examples/](./examples/)**: Working examples

---

**Last Updated**: 2025-10-27
**Maintainer**: jitokim (jitokim@users.noreply.github.com)
