"""Python Garbage Collection Monitor

Monitors Python GC behavior in production environments:
- Tracks generation 0/1/2 collection statistics
- Logs GC activity periodically for observability platforms
- Dynamically configures GC thresholds based on system memory and worker count

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
        # Auto-calculates threshold based on system memory and WORKERS env
        gc_monitor = GCMonitor(log_interval=60)
        await gc_monitor.start()
        app.state.gc_monitor = gc_monitor

        yield

        # Cleanup
        await gc_monitor.stop()

    app = FastAPI(lifespan=lifespan)

    # Or override with custom threshold if needed
    # gc_monitor = GCMonitor(threshold=(700, 10, 10), log_interval=60)
"""

import gc
import os
import asyncio
import logging
from typing import Tuple, Optional

logger = logging.getLogger(__name__)


def _get_total_memory_gb() -> float:
    """Get total system memory in GB using standard library.

    Works on Linux, macOS, and other Unix-like systems.
    Falls back to a conservative estimate if unable to detect.

    Returns:
        Total memory in GB
    """
    try:
        # Unix/Linux: use sysconf
        if hasattr(os, 'sysconf'):
            page_size = os.sysconf('SC_PAGE_SIZE')
            total_pages = os.sysconf('SC_PHYS_PAGES')
            total_bytes = page_size * total_pages
            return total_bytes / (1024 ** 3)
    except (ValueError, OSError, AttributeError):
        pass

    try:
        # Linux: parse /proc/meminfo
        with open('/proc/meminfo', 'r') as f:
            for line in f:
                if line.startswith('MemTotal:'):
                    # MemTotal: 2048000 kB
                    kb = int(line.split()[1])
                    return kb / (1024 ** 2)  # KB to GB
    except (FileNotFoundError, ValueError, IndexError):
        pass

    # Fallback: conservative estimate
    logger.warning("Unable to detect system memory, using 2GB fallback")
    return 2.0


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
            threshold: GC threshold (gen0, gen1, gen2).
                If None, calculates dynamically based on system memory and WORKERS env variable.
                Uses linear scaling: more memory per worker → higher threshold (less frequent GC).
            log_interval: Seconds between periodic GC stats logging
        """
        self.threshold = threshold or self._calculate_threshold()
        self.log_interval = log_interval
        self._monitoring_task: Optional[asyncio.Task] = None
        self._should_stop = False

    def _calculate_threshold(self) -> Tuple[int, int, int]:
        """Calculate optimal GC threshold based on system memory and worker count.

        Strategy:
        - Read WORKERS from environment variable
        - Calculate memory per worker
        - Scale threshold linearly based on memory availability
        - Baseline: 700 (Python default) for 0.5GB per worker
        - Clamp between 400-1000 to avoid extremes

        Returns:
            (gen0, gen1, gen2) threshold tuple

        Examples:
            2GB / 4 workers = 0.5GB → (700, 10, 10)
            4GB / 4 workers = 1GB → (1000, 14, 14)  # clamped
            2GB / 8 workers = 0.25GB → (400, 5, 5)  # clamped
        """
        # Read worker count from environment
        workers = int(os.getenv("WORKERS", "1"))

        # Get system memory
        total_memory_gb = _get_total_memory_gb()
        memory_per_worker_gb = total_memory_gb / workers

        # Linear scaling from baseline
        base_gen0 = 700  # Python default
        baseline_memory = 0.5  # GB per worker baseline
        scale_factor = memory_per_worker_gb / baseline_memory

        # Calculate gen0 with clamping
        gen0 = int(base_gen0 * scale_factor)
        gen0 = max(400, min(1000, gen0))  # Clamp to [400, 1000]

        # Maintain Python's default ratio (~1:70)
        gen1 = max(5, gen0 // 70)
        gen2 = max(5, gen0 // 70)

        logger.info(
            "GC threshold calculated dynamically",
            extra={
                "worker_pid": os.getpid(),
                "total_memory_gb": round(total_memory_gb, 2),
                "workers": workers,
                "memory_per_worker_gb": round(memory_per_worker_gb, 2),
                "scale_factor": round(scale_factor, 2),
                "calculated_threshold": (gen0, gen1, gen2),
            }
        )

        return (gen0, gen1, gen2)

    async def start(self):
        """Start GC monitoring.

        1. Logs initial GC state
        2. Configures GC threshold
        3. Starts periodic stats logging task
        """
        # Log initial GC state (before any changes)
        self._log_initial_state()

        # Configure GC threshold
        self._configure_threshold()

        # Start periodic monitoring
        self._should_stop = False
        self._monitoring_task = asyncio.create_task(self._monitor_loop())

        logger.info(
            "GC monitor started",
            extra={
                "worker_pid": os.getpid(),
                "threshold": self.threshold,
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
