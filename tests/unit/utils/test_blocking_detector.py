import asyncio

import pytest

from fastapi_forge.utils import EventLoopMonitor, start_event_loop_monitor, stop_event_loop_monitor


@pytest.mark.asyncio
async def test_event_loop_monitor_start_stop():
    monitor = EventLoopMonitor(check_interval=0.05, threshold=0.05)

    await monitor.start()
    await asyncio.sleep(0)  # allow background task scheduling

    assert monitor.is_running

    await monitor.stop()

    assert not monitor.is_running


@pytest.mark.asyncio
async def test_global_monitor_lifecycle():
    monitor = await start_event_loop_monitor(check_interval=0.05, threshold=0.05)

    await asyncio.sleep(0)
    assert monitor.is_running

    await stop_event_loop_monitor()

    assert not monitor.is_running
