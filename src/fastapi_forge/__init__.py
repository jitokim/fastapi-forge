"""FastAPI Forge - Production-ready toolkit for FastAPI applications.

FastAPI Forge provides battle-tested patterns and utilities for building
production-ready FastAPI applications with minimal boilerplate.

Features:
- 🪵 Production logging (Gunicorn + Datadog optimized)
- 🚀 FastAPI templates and best practices
- 🤖 Langchain integration utilities
- 📊 Monitoring and observability
- ⚙️ Gunicorn/Uvicorn configurations

Quick Start:
    ```python
    from fastapi_forge.logging import configure_logging

    # Configure production logging
    configure_logging()

    from fastapi import FastAPI
    app = FastAPI()
    ```

For more information, visit: https://github.com/fastapi-forge/fastapi-forge
"""

__version__ = "0.1.0"
__author__ = "FastAPI Forge Contributors"
__license__ = "MIT"

__all__ = ["__version__"]
