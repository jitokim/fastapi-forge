"""Utilities for FastAPI applications.

This module provides various utility functions and classes for FastAPI applications,
including event loop monitoring and other production-ready tools.
"""

from .blocking_detector import (
    EventLoopMonitor,
    start_event_loop_monitor,
    stop_event_loop_monitor,
)

__all__ = [
    "EventLoopMonitor",
    "start_event_loop_monitor",
    "stop_event_loop_monitor",
]
