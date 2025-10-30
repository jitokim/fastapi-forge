"""Monitoring utilities for FastAPI Forge.

This module provides monitoring tools for production FastAPI applications:
- GCMonitor: Python garbage collection monitoring and tuning

Usage:
    from fastapi_forge.monitoring import GCMonitor

    @asynccontextmanager
    async def lifespan(app):
        gc_monitor = GCMonitor(threshold=(500, 5, 5), log_interval=60)
        await gc_monitor.start()

        yield

        await gc_monitor.stop()
"""

from .gc_monitor import GCMonitor

__all__ = ["GCMonitor"]
