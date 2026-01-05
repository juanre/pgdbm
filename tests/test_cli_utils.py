import asyncio
import threading

import pytest

from pgdbm.cli.utils import run_async


def test_run_async_without_running_loop() -> None:
    assert run_async(asyncio.sleep(0, result=123)) == 123


@pytest.mark.asyncio
async def test_run_async_with_running_loop_uses_helper_thread() -> None:
    async def get_thread_id() -> int:
        await asyncio.sleep(0)
        return threading.get_ident()

    result_thread_id = run_async(get_thread_id())
    assert result_thread_id != threading.get_ident()


@pytest.mark.asyncio
async def test_run_async_with_running_loop_propagates_exceptions() -> None:
    async def boom() -> None:
        await asyncio.sleep(0)
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        run_async(boom())
