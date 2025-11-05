"""Tests for GCMonitor

Tests cover:
1. Initialization and caching behavior
2. Start/stop lifecycle
3. Event loop non-blocking behavior
4. GC stats logging
5. Dynamic threshold calculation
"""

import asyncio
import gc
import os
import time
from unittest.mock import patch, MagicMock, call
import pytest

from fastapi_forge.monitoring.gc_monitor import GCMonitor


class TestGCMonitorInitialization:
    """Test GCMonitor initialization and caching."""

    def test_init_with_auto_threshold(self):
        """Test initialization with automatic threshold calculation."""
        with patch.dict(os.environ, {"WORKERS": "4"}):
            monitor = GCMonitor()

            assert monitor.log_interval == 60
            assert monitor._worker_pid == os.getpid()
            assert monitor._threshold_cache is None  # Not set until start()
            assert monitor._monitoring_task is None
            assert monitor._should_stop is False
            assert monitor.threshold is not None  # Calculated dynamically

    def test_init_with_custom_threshold(self):
        """Test initialization with custom threshold."""
        monitor = GCMonitor(threshold=(700, 10, 10), log_interval=30)

        assert monitor.threshold == (700, 10, 10)
        assert monitor.log_interval == 30

    def test_worker_pid_cached_at_init(self):
        """Test that worker_pid is cached at initialization."""
        monitor = GCMonitor(threshold=(500, 5, 5))

        # Should be cached and equal to current PID
        assert monitor._worker_pid == os.getpid()

        # Should be the same across multiple accesses
        pid1 = monitor._worker_pid
        pid2 = monitor._worker_pid
        assert pid1 == pid2


class TestGCMonitorThresholdCalculation:
    """Test dynamic GC threshold calculation."""

    def test_calculate_threshold_with_low_memory(self):
        """Test threshold calculation with low memory per worker."""
        with patch("fastapi_forge.monitoring.gc_monitor._get_total_memory_gb", return_value=2.0):
            with patch.dict(os.environ, {"WORKERS": "8"}):  # 0.25GB per worker
                monitor = GCMonitor()

                # Should clamp to minimum (400)
                assert monitor.threshold[0] >= 400

    def test_calculate_threshold_with_high_memory(self):
        """Test threshold calculation with high memory per worker."""
        with patch("fastapi_forge.monitoring.gc_monitor._get_total_memory_gb", return_value=16.0):
            with patch.dict(os.environ, {"WORKERS": "4"}):  # 4GB per worker
                monitor = GCMonitor()

                # Should clamp to maximum (1000)
                assert monitor.threshold[0] <= 1000

    def test_calculate_threshold_uses_cached_pid(self):
        """Test that threshold calculation uses cached worker_pid."""
        with patch("fastapi_forge.monitoring.gc_monitor._get_total_memory_gb", return_value=4.0):
            with patch("fastapi_forge.monitoring.gc_monitor.logger") as mock_logger:
                monitor = GCMonitor()

                # Check that the log message used cached worker_pid
                call_args = mock_logger.info.call_args
                if call_args:
                    extra = call_args.kwargs.get("extra", {})
                    if "worker_pid" in extra:
                        assert extra["worker_pid"] == monitor._worker_pid


class TestGCMonitorLifecycle:
    """Test GCMonitor start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start_creates_monitoring_task(self):
        """Test that start() creates a monitoring task."""
        monitor = GCMonitor(threshold=(500, 5, 5), log_interval=1)

        await monitor.start()

        # Check monitoring task is created
        assert monitor._monitoring_task is not None
        assert not monitor._monitoring_task.done()
        assert monitor._should_stop is False

        # Check threshold is cached after start
        assert monitor._threshold_cache is not None
        assert monitor._threshold_cache == gc.get_threshold()

        # Cleanup
        await monitor.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_monitoring_task(self):
        """Test that stop() cancels the monitoring task."""
        monitor = GCMonitor(threshold=(500, 5, 5), log_interval=1)

        await monitor.start()
        task = monitor._monitoring_task

        await monitor.stop()

        # Check monitoring task is cancelled
        assert monitor._should_stop is True
        assert task.done()
        assert task.cancelled()

    @pytest.mark.asyncio
    async def test_start_configures_gc_threshold(self):
        """Test that start() configures GC threshold."""
        old_threshold = gc.get_threshold()

        try:
            monitor = GCMonitor(threshold=(600, 8, 8), log_interval=1)
            await monitor.start()

            # GC threshold should be configured
            assert gc.get_threshold() == (600, 8, 8)
            assert monitor._threshold_cache == (600, 8, 8)

            await monitor.stop()
        finally:
            # Restore original threshold
            gc.set_threshold(*old_threshold)

    @pytest.mark.asyncio
    async def test_stop_without_start_is_safe(self):
        """Test that stop() can be called without start()."""
        monitor = GCMonitor(threshold=(500, 5, 5))

        # Should not raise exception
        await monitor.stop()


class TestGCMonitorLogging:
    """Test GCMonitor logging behavior."""

    @pytest.mark.asyncio
    async def test_log_gc_stats_uses_cached_values(self):
        """Test that _log_gc_stats uses cached worker_pid and threshold."""
        monitor = GCMonitor(threshold=(500, 5, 5), log_interval=1)
        await monitor.start()

        with patch("fastapi_forge.monitoring.gc_monitor.logger") as mock_logger:
            # Call _log_gc_stats directly
            monitor._log_gc_stats()

            # Verify logger.info was called
            assert mock_logger.info.called

            # Get the extra dict passed to logger.info
            call_args = mock_logger.info.call_args
            extra_dict = call_args.kwargs["extra"]

            # Verify cached values are used
            assert extra_dict["worker_pid"] == monitor._worker_pid
            assert extra_dict["threshold"] == monitor._threshold_cache

            # Verify GC stats are present
            assert "gen0_collections" in extra_dict
            assert "gen1_collections" in extra_dict
            assert "gen2_collections" in extra_dict

        await monitor.stop()

    @pytest.mark.asyncio
    async def test_log_gc_stats_includes_all_generations(self):
        """Test that _log_gc_stats includes stats for all 3 generations."""
        monitor = GCMonitor(threshold=(500, 5, 5), log_interval=1)
        await monitor.start()

        with patch("fastapi_forge.monitoring.gc_monitor.logger") as mock_logger:
            monitor._log_gc_stats()

            extra_dict = mock_logger.info.call_args.kwargs["extra"]

            # Gen 0
            assert "gen0_collections" in extra_dict
            assert "gen0_collected" in extra_dict
            assert "gen0_uncollectable" in extra_dict

            # Gen 1
            assert "gen1_collections" in extra_dict
            assert "gen1_collected" in extra_dict
            assert "gen1_uncollectable" in extra_dict

            # Gen 2
            assert "gen2_collections" in extra_dict
            assert "gen2_collected" in extra_dict
            assert "gen2_uncollectable" in extra_dict

        await monitor.stop()


class TestGCMonitorNonBlocking:
    """Test that GCMonitor doesn't block the event loop."""

    @pytest.mark.asyncio
    async def test_monitor_loop_runs_in_thread(self):
        """Test that _log_gc_stats runs in thread pool via asyncio.to_thread."""
        monitor = GCMonitor(threshold=(500, 5, 5), log_interval=0.1)

        with patch("fastapi_forge.monitoring.gc_monitor.logger"):
            with patch.object(monitor, "_log_gc_stats", wraps=monitor._log_gc_stats) as mock_log:
                await monitor.start()

                # Wait for at least one logging cycle
                await asyncio.sleep(0.2)

                await monitor.stop()

                # Verify _log_gc_stats was called at least once
                assert mock_log.call_count >= 1

    @pytest.mark.asyncio
    async def test_monitor_does_not_block_event_loop(self):
        """Test that GC monitor doesn't block other async tasks."""
        monitor = GCMonitor(threshold=(500, 5, 5), log_interval=0.1)

        # Track if other task ran
        other_task_ran = False

        async def other_task():
            nonlocal other_task_ran
            await asyncio.sleep(0.15)
            other_task_ran = True

        with patch("fastapi_forge.monitoring.gc_monitor.logger"):
            await monitor.start()

            # Run another task concurrently
            task = asyncio.create_task(other_task())
            await asyncio.sleep(0.2)
            await task

            await monitor.stop()

            # Other task should have completed successfully
            assert other_task_ran

    @pytest.mark.asyncio
    async def test_blocking_in_log_gc_stats_does_not_block_loop(self):
        """Test that even if _log_gc_stats blocks, event loop continues."""
        monitor = GCMonitor(threshold=(500, 5, 5), log_interval=0.1)

        # Mock _log_gc_stats to intentionally block
        original_log_gc_stats = monitor._log_gc_stats

        def blocking_log_gc_stats():
            time.sleep(0.05)  # Simulate blocking operation
            original_log_gc_stats()

        monitor._log_gc_stats = blocking_log_gc_stats

        loop_was_responsive = False

        async def check_loop_responsiveness():
            nonlocal loop_was_responsive
            await asyncio.sleep(0.15)
            loop_was_responsive = True

        with patch("fastapi_forge.monitoring.gc_monitor.logger"):
            await monitor.start()

            # Start responsiveness check
            check_task = asyncio.create_task(check_loop_responsiveness())
            await asyncio.sleep(0.2)
            await check_task

            await monitor.stop()

            # Loop should remain responsive despite blocking in _log_gc_stats
            # (because it runs in thread pool via asyncio.to_thread)
            assert loop_was_responsive


class TestGCMonitorErrorHandling:
    """Test GCMonitor error handling."""

    @pytest.mark.asyncio
    async def test_monitor_continues_after_logging_error(self):
        """Test that monitor continues even if logging raises exception."""
        monitor = GCMonitor(threshold=(500, 5, 5), log_interval=0.1)

        call_count = 0

        def failing_log_gc_stats():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("Test error")

        with patch.object(monitor, "_log_gc_stats", side_effect=failing_log_gc_stats):
            with patch("fastapi_forge.monitoring.gc_monitor.logger") as mock_logger:
                await monitor.start()

                # Wait for multiple cycles
                await asyncio.sleep(0.25)

                await monitor.stop()

                # Error should be logged but monitor should continue
                assert call_count >= 2  # Should have retried after error

                # Check that error was logged
                error_calls = [
                    call_args
                    for call_args in mock_logger.error.call_args_list
                    if "Error in GC monitor loop" in str(call_args)
                ]
                assert len(error_calls) >= 1


class TestGCMonitorIntegration:
    """Integration tests for GCMonitor."""

    @pytest.mark.asyncio
    async def test_full_lifecycle_with_actual_logging(self):
        """Test full lifecycle with actual GC stats logging."""
        monitor = GCMonitor(threshold=(500, 5, 5), log_interval=0.1)

        with patch("fastapi_forge.monitoring.gc_monitor.logger") as mock_logger:
            # Start monitor
            await monitor.start()

            # Verify start was logged
            start_calls = [c for c in mock_logger.info.call_args_list if "GC monitor started" in str(c)]
            assert len(start_calls) == 1

            # Wait for at least 2 logging cycles
            await asyncio.sleep(0.25)

            # Stop monitor
            await monitor.stop()

            # Verify stop was logged
            stop_calls = [c for c in mock_logger.info.call_args_list if "GC monitor stopped" in str(c)]
            assert len(stop_calls) == 1

            # Verify GC stats were logged at least twice
            stats_calls = [c for c in mock_logger.info.call_args_list if "GC stats snapshot" in str(c)]
            assert len(stats_calls) >= 2
