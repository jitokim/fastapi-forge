"""Event loop blocking detection for FastAPI applications.

This module provides a background monitor that detects when the event loop
is blocked by measuring the actual delay of scheduled asyncio.sleep() calls.

Unlike the naive approach of comparing time.perf_counter() and loop.time()
(which both use the same monotonic clock), this implementation actually
detects blocking by checking if scheduled tasks are delayed.

Usage:
    from component.utils.middleware.blocking_detector import EventLoopMonitor

    monitor = EventLoopMonitor(check_interval=0.1, threshold=0.05)
    await monitor.start()
    # ... run application ...
    await monitor.stop()

This module is part of component.utils and is shared across multiple services
(middle, collection, etc.) for reusability.
"""

import asyncio
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)


class EventLoopMonitor:
    """Monitor event loop for blocking operations.

    This monitor runs a background task that periodically schedules an
    asyncio.sleep() and measures how long it actually takes. If the actual
    delay is significantly longer than requested, it indicates that the
    event loop was blocked by synchronous operations.

    Attributes:
        check_interval: How often to check (in seconds). Default: 0.1s (100ms)
        threshold: Maximum acceptable excess delay (in seconds). Default: 0.05s (50ms)

    Example:
        monitor = EventLoopMonitor(check_interval=0.1, threshold=0.05)
        await monitor.start()  # Start monitoring in background
        # ... application runs ...
        await monitor.stop()   # Clean shutdown
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
            check_interval: Interval between checks in seconds (default: 0.1s)
            threshold: Maximum acceptable excess delay in seconds (default: 0.05s)
            log_excess_only: If True, only log when threshold is exceeded.
                           If False, log all measurements (for debugging).
            capture_stack_trace: If True, capture stack traces of running tasks
                               when blocking is detected (default: True).
        """
        self.check_interval = check_interval
        self.threshold = threshold
        self.log_excess_only = log_excess_only
        self.capture_stack_trace = capture_stack_trace
        self._task: Optional[asyncio.Task] = None
        self._running = False

    def _capture_task_stacks(self) -> str:
        """Capture stack traces of all running tasks.

        Returns:
            A formatted string containing stack traces of all tasks.
        """
        try:
            tasks = asyncio.all_tasks()
            stack_info = []

            for task in tasks:
                # Skip our own monitor task
                if task == self._task:
                    continue

                # Get task name and coroutine info
                task_name = task.get_name()
                coro = task.get_coro()
                coro_name = f"{coro.__qualname__}" if hasattr(coro, "__qualname__") else str(coro)

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

                        stack_lines.append(f"  File \"{filename}\", line {lineno}, in {func_name}")

                    if stack_lines:
                        stack_info.append(f"Task: {task_name} ({coro_name})")
                        stack_info.extend(stack_lines)
                        stack_info.append("")  # Empty line between tasks

            if stack_info:
                return "\n".join(stack_info)
            else:
                return "No user task stacks available"

        except Exception as e:
            return f"Error capturing stacks: {e}"

    async def _monitor_loop(self):
        """Background task that monitors event loop health.

        This task runs indefinitely until stopped. It schedules an asyncio.sleep()
        for check_interval seconds, then measures how long it actually took.

        If the actual delay exceeds (check_interval + threshold), it logs a warning
        indicating that the event loop was blocked.
        """
        logger.info(
            "Event loop monitor started",
            extra={
                "check_interval_ms": round(self.check_interval * 1000, 1),
                "threshold_ms": round(self.threshold * 1000, 1),
            }
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
                            f"[EVENT_LOOP_BLOCKED] Event loop blocking detected\n\nRunning tasks:\n{stack_trace}",
                            extra=log_extra
                        )
                    else:
                        logger.warning(
                            "[EVENT_LOOP_BLOCKED] Event loop blocking detected",
                            extra=log_extra
                        )
                elif not self.log_excess_only:
                    logger.info(
                        "[EVENT_LOOP_OK] Event loop healthy",
                        extra={
                            "expected_delay_ms": round(self.check_interval * 1000, 3),
                            "actual_delay_ms": round(actual_delay * 1000, 3),
                            "excess_delay_ms": round(excess_delay * 1000, 3),
                        }
                    )

            except asyncio.CancelledError:
                # Normal shutdown
                logger.info("Event loop monitor stopping...")
                break
            except Exception as e:
                # Log errors but keep monitoring
                logger.error(
                    "Error in event loop monitor",
                    extra={"error": str(e)},
                    exc_info=True
                )
                # Brief pause before retrying
                await asyncio.sleep(1.0)

    async def start(self):
        """Start the event loop monitor.

        Creates a background task that monitors the event loop.
        This should be called during application startup.

        Note: This method is idempotent - calling it multiple times
        won't create multiple monitor tasks.
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
        This should be called during application shutdown.

        Note: This method is idempotent - calling it multiple times is safe.
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
        """Check if the monitor is currently running."""
        return self._running and self._task is not None and not self._task.done()


# Convenience function for single-instance usage
_global_monitor: Optional[EventLoopMonitor] = None


async def start_event_loop_monitor(
    check_interval: float = 0.1,
    threshold: float = 0.05,
    log_excess_only: bool = True,
    capture_stack_trace: bool = True,
) -> EventLoopMonitor:
    """Start a global event loop monitor.

    This is a convenience function for applications that want a single
    global monitor instance.

    Args:
        check_interval: Interval between checks in seconds
        threshold: Maximum acceptable excess delay in seconds
        log_excess_only: Only log when threshold is exceeded
        capture_stack_trace: Capture stack traces when blocking is detected

    Returns:
        The EventLoopMonitor instance

    Example:
        # In FastAPI lifespan
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            monitor = await start_event_loop_monitor()
            yield
            await stop_event_loop_monitor()
    """
    global _global_monitor

    if _global_monitor is not None:
        logger.warning("Global event loop monitor already exists")
        return _global_monitor

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
    """
    global _global_monitor

    if _global_monitor is None:
        logger.warning("No global event loop monitor to stop")
        return

    await _global_monitor.stop()
    _global_monitor = None
