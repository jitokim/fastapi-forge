"""Python Garbage Collection Monitor

Monitors Python GC behavior in production environments:
- Tracks generation 0/1/2 collection statistics
- Logs GC activity periodically for observability platforms
- Configures GC thresholds based on memory constraints

Useful for:
- Debugging memory issues in production
- Correlating OOM events with GC patterns
- Identifying memory leaks (via uncollectable objects)
- Optimizing GC thresholds for specific workloads

Example:
    from fastapi import FastAPI
    from contextlib import asynccontextmanager
    from fastapi_forge.monitoring import GCMonitor

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Initialize GC monitor
        gc_monitor = GCMonitor(
            threshold=(500, 5, 5),  # More frequent GC for memory-constrained environments
            log_interval=60,        # Log stats every 60 seconds
        )
        await gc_monitor.start()
        app.state.gc_monitor = gc_monitor

        yield

        # Cleanup
        await gc_monitor.stop()

    app = FastAPI(lifespan=lifespan)
"""

import gc
import os
import asyncio
import logging
from typing import Tuple, Optional

logger = logging.getLogger(__name__)


class GCMonitor:
    """Python GC monitoring and configuration manager.

    Monitors Python's generational garbage collector and provides
    detailed statistics for debugging memory issues in production.

    GC Generations:
        - gen0 (young): Recently created objects
        - gen1 (middle): Objects that survived gen0 collection
        - gen2 (old): Long-lived objects

    Python Default Threshold: (700, 10, 10)
        - gen0: Collect after 700 objects allocated
        - gen1: Collect after gen0 runs 10 times
        - gen2: Collect after gen1 runs 10 times

    Attributes:
        threshold: GC threshold tuple (gen0, gen1, gen2)
        log_interval: Seconds between GC stats logging
    """

    def __init__(
        self,
        threshold: Optional[Tuple[int, int, int]] = None,
        log_interval: int = 60,
    ):
        """Initialize GC monitor.

        Args:
            threshold: GC threshold (gen0, gen1, gen2)
                None: Keep Python default (700, 10, 10)
                (500, 5, 5): More frequent GC for memory-constrained environments
                (1000, 20, 20): Less frequent GC for CPU-constrained environments
            log_interval: Seconds between periodic GC stats logging
        """
        self.threshold = threshold
        self.log_interval = log_interval
        self._monitoring_task: Optional[asyncio.Task] = None
        self._should_stop = False

    async def start(self):
        """Start GC monitoring.

        1. Logs initial GC state
        2. Configures GC threshold (if specified)
        3. Starts periodic stats logging task
        """
        # Log initial GC state (before any changes)
        self._log_initial_state()

        # Configure GC threshold (if specified)
        if self.threshold is not None:
            self._configure_threshold()

        # Start periodic monitoring
        self._should_stop = False
        self._monitoring_task = asyncio.create_task(self._monitor_loop())

        logger.info(
            "GC monitor started",
            extra={
                "worker_pid": os.getpid(),
                "threshold": gc.get_threshold(),
                "log_interval": self.log_interval,
            }
        )

    async def stop(self):
        """Stop GC monitoring."""
        self._should_stop = True

        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass

        logger.info(
            "GC monitor stopped",
            extra={"worker_pid": os.getpid()}
        )

    def _log_initial_state(self):
        """Log initial GC state before any configuration."""
        stats = gc.get_stats()

        logger.info(
            "GC initial state",
            extra={
                "worker_pid": os.getpid(),
                "threshold": gc.get_threshold(),
                "gc_enabled": gc.isenabled(),
                "gen0_collections": stats[0]["collections"],
                "gen0_collected": stats[0]["collected"],
                "gen0_uncollectable": stats[0]["uncollectable"],
                "gen1_collections": stats[1]["collections"],
                "gen1_collected": stats[1]["collected"],
                "gen1_uncollectable": stats[1]["uncollectable"],
                "gen2_collections": stats[2]["collections"],
                "gen2_collected": stats[2]["collected"],
                "gen2_uncollectable": stats[2]["uncollectable"],
            }
        )

    def _configure_threshold(self):
        """Configure GC threshold."""
        old_threshold = gc.get_threshold()
        gc.set_threshold(*self.threshold)

        logger.info(
            "GC threshold configured",
            extra={
                "worker_pid": os.getpid(),
                "old_threshold": old_threshold,
                "new_threshold": gc.get_threshold(),
            }
        )

    async def _monitor_loop(self):
        """Periodic GC stats logging loop."""
        while not self._should_stop:
            try:
                await asyncio.sleep(self.log_interval)
                self._log_gc_stats()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(
                    f"Error in GC monitor loop: {e}",
                    extra={"worker_pid": os.getpid()},
                    exc_info=True
                )

    def _log_gc_stats(self):
        """Log current GC statistics.

        Statistics include:
        - collections: Number of times this generation was collected
        - collected: Number of objects collected
        - uncollectable: Number of objects that couldn't be collected (memory leak indicator)
        """
        stats = gc.get_stats()

        logger.info(
            "GC stats snapshot",
            extra={
                "worker_pid": os.getpid(),
                "threshold": gc.get_threshold(),
                # Generation 0 (young objects)
                "gen0_collections": stats[0]["collections"],
                "gen0_collected": stats[0]["collected"],
                "gen0_uncollectable": stats[0]["uncollectable"],
                # Generation 1 (middle-aged objects)
                "gen1_collections": stats[1]["collections"],
                "gen1_collected": stats[1]["collected"],
                "gen1_uncollectable": stats[1]["uncollectable"],
                # Generation 2 (old objects)
                "gen2_collections": stats[2]["collections"],
                "gen2_collected": stats[2]["collected"],
                "gen2_uncollectable": stats[2]["uncollectable"],
            }
        )


__all__ = ["GCMonitor"]
