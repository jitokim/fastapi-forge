"""Event loop blocking detection for FastAPI applications.

This module provides a background monitor that detects when the event loop
is blocked by measuring the actual delay of scheduled asyncio.sleep() calls.

Unlike naive approaches that compare time.perf_counter() and loop.time()
(which both use the same monotonic clock), this implementation actually
detects blocking by checking if scheduled tasks are delayed beyond acceptable
thresholds.

The monitor captures stack traces of running tasks when blocking is detected,
helping identify the source of synchronous operations that block the event loop.

Usage:
    Basic usage with EventLoopMonitor:
        ```python
        from fastapi_forge.utils.blocking_detector import EventLoopMonitor

        monitor = EventLoopMonitor(check_interval=0.1, threshold=0.05)
        await monitor.start()
        # ... run application ...
        await monitor.stop()
        ```

    FastAPI integration with lifespan:
        ```python
        from contextlib import asynccontextmanager
        from fastapi import FastAPI
        from fastapi_forge.utils.blocking_detector import (
            start_event_loop_monitor,
            stop_event_loop_monitor,
        )

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            # Start monitoring on startup
            monitor = await start_event_loop_monitor(
                check_interval=0.1,
                threshold=0.05,
                capture_stack_trace=True,
            )
            yield
            # Stop monitoring on shutdown
            await stop_event_loop_monitor()

        app = FastAPI(lifespan=lifespan)
        ```

Environment Variables:
    - EVENT_LOOP_CHECK_INTERVAL: Check interval in seconds (default: 0.1)
    - EVENT_LOOP_THRESHOLD: Blocking threshold in seconds (default: 0.05)
    - EVENT_LOOP_CAPTURE_STACKS: Enable stack trace capture (default: true)

Performance Impact:
    The monitor has minimal overhead:
    - Check interval: 100ms (default)
    - CPU usage: <0.1% per check
    - Memory: ~1-2KB per captured stack trace

When to Use:
    ✅ Production environments with async workloads
    ✅ Debugging performance issues
    ✅ Detecting blocking I/O operations
    ✅ Monitoring long-running synchronous code

    ❌ CPU-bound applications (expected blocking)
    ❌ Single-threaded synchronous apps

Author: FastAPI Forge Contributors
"""

import asyncio
import logging
import os
import time
from typing import Optional, List

logger = logging.getLogger(__name__)


class EventLoopMonitor:
    """Monitor event loop for blocking operations.

    This monitor runs a background task that periodically schedules an
    asyncio.sleep() and measures how long it actually takes. If the actual
    delay is significantly longer than requested, it indicates that the
    event loop was blocked by synchronous operations.

    The monitor can capture stack traces of all running tasks when blocking
    is detected, which helps identify the culprit causing the blockage.

    Attributes:
        check_interval: How often to check in seconds (default: 0.1s / 100ms)
        threshold: Maximum acceptable excess delay in seconds (default: 0.05s / 50ms)
        log_excess_only: Only log when threshold is exceeded (default: True)
        capture_stack_trace: Capture stack traces on blocking detection (default: True)

    Example:
        ```python
        # Create and start monitor
        monitor = EventLoopMonitor(check_interval=0.1, threshold=0.05)
        await monitor.start()

        # Check if running
        if monitor.is_running:
            print("Monitor is active")

        # Clean shutdown
        await monitor.stop()
        ```

    Warning:
        Setting check_interval too low (<0.01s) may cause false positives.
        Setting threshold too low (<0.01s) will trigger many warnings.
    """

    def __init__(
        self,
        check_interval: float = 0.1,
        threshold: float = 0.05,
        log_excess_only: bool = True,
        capture_stack_trace: bool = True,
    ):
        """Initialize the event loop monitor.

        Args:
            check_interval: Interval between checks in seconds.
                Recommended: 0.1s (100ms) for production.
            threshold: Maximum acceptable excess delay in seconds.
                Recommended: 0.05s (50ms) for most applications.
            log_excess_only: If True, only log when threshold is exceeded.
                Set to False for detailed debugging (verbose output).
            capture_stack_trace: If True, capture stack traces of running tasks
                when blocking is detected. Helps identify blocking code.

        Raises:
            ValueError: If check_interval or threshold is negative or zero.
        """
        if check_interval <= 0:
            raise ValueError(f"check_interval must be positive, got {check_interval}")
        if threshold <= 0:
            raise ValueError(f"threshold must be positive, got {threshold}")

        self.check_interval = check_interval
        self.threshold = threshold
        self.log_excess_only = log_excess_only
        self.capture_stack_trace = capture_stack_trace
        self._task: Optional[asyncio.Task] = None
        self._running = False

    def _capture_task_stacks(self) -> str:
        """Capture stack traces of all running asyncio tasks.

        This method iterates through all tasks in the current event loop
        and extracts their stack frames. It filters out internal asyncio/uvloop
        frames for better readability.

        Returns:
            A formatted string containing stack traces of user tasks,
            or an error message if capture fails.

        Note:
            The monitor's own task is excluded from the output.
        """
        try:
            tasks = asyncio.all_tasks()
            stack_info: List[str] = []

            for task in tasks:
                # Skip our own monitor task
                if task == self._task:
                    continue

                # Get task name and coroutine info
                task_name = task.get_name()
                coro = task.get_coro()
                coro_name = (
                    f"{coro.__qualname__}" if hasattr(coro, "__qualname__") else str(coro)
                )

                # Extract stack frames
                frames = task.get_stack()
                if frames:
                    stack_lines = []
                    for frame in frames:
                        filename = frame.f_code.co_filename
                        lineno = frame.f_lineno
                        func_name = frame.f_code.co_name

                        # Skip internal asyncio/uvloop frames for readability
                        if "asyncio" in filename or "uvloop" in filename:
                            continue

                        stack_lines.append(
                            f'  File "{filename}", line {lineno}, in {func_name}'
                        )

                    if stack_lines:
                        stack_info.append(f"Task: {task_name} ({coro_name})")
                        stack_info.extend(stack_lines)
                        stack_info.append("")  # Empty line between tasks

            if stack_info:
                return "\n".join(stack_info)
            else:
                return "No user task stacks available (all tasks are internal)"

        except Exception as e:
            return f"Error capturing stacks: {e}"

    async def _monitor_loop(self):
        """Background task that monitors event loop health.

        This task runs indefinitely until stopped. It schedules an asyncio.sleep()
        for check_interval seconds, then measures how long it actually took.

        If the actual delay exceeds (check_interval + threshold), it logs a warning
        indicating that the event loop was blocked, along with:
        - Expected vs actual delay
        - Excess delay
        - Blocking ratio (percentage)
        - Stack traces of running tasks (if enabled)
        """
        logger.info(
            "Event loop monitor started",
            extra={
                "check_interval_ms": round(self.check_interval * 1000, 1),
                "threshold_ms": round(self.threshold * 1000, 1),
                "capture_stacks": self.capture_stack_trace,
            },
        )

        while self._running:
            try:
                start_time = time.perf_counter()
                await asyncio.sleep(self.check_interval)
                actual_delay = time.perf_counter() - start_time

                # Calculate excess delay beyond the requested sleep time
                excess_delay = actual_delay - self.check_interval

                # Log if threshold exceeded or if debugging all measurements
                if excess_delay > self.threshold:
                    log_extra = {
                        "expected_delay_ms": round(self.check_interval * 1000, 3),
                        "actual_delay_ms": round(actual_delay * 1000, 3),
                        "excess_delay_ms": round(excess_delay * 1000, 3),
                        "blocking_ratio": round(excess_delay / self.check_interval * 100, 1),
                    }

                    # Capture stack traces if enabled
                    if self.capture_stack_trace:
                        stack_trace = self._capture_task_stacks()
                        logger.warning(
                            f"[EVENT_LOOP_BLOCKED] Event loop blocking detected\n\n"
                            f"Running tasks:\n{stack_trace}",
                            extra=log_extra,
                        )
                    else:
                        logger.warning(
                            "[EVENT_LOOP_BLOCKED] Event loop blocking detected", extra=log_extra
                        )
                elif not self.log_excess_only:
                    # Debug mode: log all measurements
                    logger.info(
                        "[EVENT_LOOP_OK] Event loop healthy",
                        extra={
                            "expected_delay_ms": round(self.check_interval * 1000, 3),
                            "actual_delay_ms": round(actual_delay * 1000, 3),
                            "excess_delay_ms": round(excess_delay * 1000, 3),
                        },
                    )

            except asyncio.CancelledError:
                # Normal shutdown
                logger.info("Event loop monitor stopping...")
                break
            except Exception as e:
                # Log errors but keep monitoring
                logger.error(
                    "Error in event loop monitor", extra={"error": str(e)}, exc_info=True
                )
                # Brief pause before retrying
                await asyncio.sleep(1.0)

        logger.info("Event loop monitor stopped")

    async def start(self):
        """Start the event loop monitor.

        Creates a background task that monitors the event loop.
        This should be called during application startup (e.g., FastAPI lifespan).

        Note:
            This method is idempotent - calling it multiple times
            won't create multiple monitor tasks.

        Example:
            ```python
            @asynccontextmanager
            async def lifespan(app: FastAPI):
                monitor = EventLoopMonitor()
                await monitor.start()
                yield
                await monitor.stop()
            ```
        """
        if self._running:
            logger.warning("Event loop monitor already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("Event loop monitor task created")

    async def stop(self):
        """Stop the event loop monitor.

        Cancels the background monitoring task and waits for it to finish.
        This should be called during application shutdown (e.g., FastAPI lifespan).

        Note:
            This method is idempotent - calling it multiple times is safe.

        Example:
            ```python
            @asynccontextmanager
            async def lifespan(app: FastAPI):
                monitor = EventLoopMonitor()
                await monitor.start()
                yield
                await monitor.stop()  # Clean shutdown
            ```
        """
        if not self._running:
            logger.warning("Event loop monitor not running")
            return

        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        logger.info("Event loop monitor stopped")

    @property
    def is_running(self) -> bool:
        """Check if the monitor is currently running.

        Returns:
            True if the monitor task is running and not done, False otherwise.
        """
        return self._running and self._task is not None and not self._task.done()


# ============================================================================
# Convenience functions for single-instance (global) usage
# ============================================================================

_global_monitor: Optional[EventLoopMonitor] = None


async def start_event_loop_monitor(
    check_interval: Optional[float] = None,
    threshold: Optional[float] = None,
    log_excess_only: bool = True,
    capture_stack_trace: Optional[bool] = None,
) -> EventLoopMonitor:
    """Start a global event loop monitor.

    This is a convenience function for applications that want a single
    global monitor instance. Parameters can be overridden via environment
    variables:
    - EVENT_LOOP_CHECK_INTERVAL (default: 0.1)
    - EVENT_LOOP_THRESHOLD (default: 0.05)
    - EVENT_LOOP_CAPTURE_STACKS (default: true)

    Args:
        check_interval: Interval between checks in seconds.
            If None, reads from EVENT_LOOP_CHECK_INTERVAL env var.
        threshold: Maximum acceptable excess delay in seconds.
            If None, reads from EVENT_LOOP_THRESHOLD env var.
        log_excess_only: Only log when threshold is exceeded.
        capture_stack_trace: Capture stack traces when blocking is detected.
            If None, reads from EVENT_LOOP_CAPTURE_STACKS env var.

    Returns:
        The EventLoopMonitor instance.

    Raises:
        Warning: If a global monitor already exists (returns existing instance).

    Example:
        ```python
        from contextlib import asynccontextmanager
        from fastapi import FastAPI
        from fastapi_forge.utils.blocking_detector import (
            start_event_loop_monitor,
            stop_event_loop_monitor,
        )

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            # Start on application startup
            monitor = await start_event_loop_monitor()
            yield
            # Stop on application shutdown
            await stop_event_loop_monitor()

        app = FastAPI(lifespan=lifespan)
        ```
    """
    global _global_monitor

    if _global_monitor is not None:
        logger.warning("Global event loop monitor already exists, returning existing instance")
        return _global_monitor

    # Read from environment variables if not provided
    if check_interval is None:
        check_interval = float(os.getenv("EVENT_LOOP_CHECK_INTERVAL", "0.1"))
    if threshold is None:
        threshold = float(os.getenv("EVENT_LOOP_THRESHOLD", "0.05"))
    if capture_stack_trace is None:
        capture_stack_trace = os.getenv("EVENT_LOOP_CAPTURE_STACKS", "true").lower() == "true"

    _global_monitor = EventLoopMonitor(
        check_interval=check_interval,
        threshold=threshold,
        log_excess_only=log_excess_only,
        capture_stack_trace=capture_stack_trace,
    )
    await _global_monitor.start()
    return _global_monitor


async def stop_event_loop_monitor():
    """Stop the global event loop monitor.

    This is a convenience function to stop the monitor started by
    start_event_loop_monitor().

    Note:
        This is idempotent - calling it multiple times is safe.

    Example:
        ```python
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            await start_event_loop_monitor()
            yield
            await stop_event_loop_monitor()  # Clean shutdown
        ```
    """
    global _global_monitor

    if _global_monitor is None:
        logger.warning("No global event loop monitor to stop")
        return

    await _global_monitor.stop()
    _global_monitor = None


__all__ = [
    "EventLoopMonitor",
    "start_event_loop_monitor",
    "stop_event_loop_monitor",
]
