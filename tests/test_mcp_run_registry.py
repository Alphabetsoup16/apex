from __future__ import annotations

import asyncio

import pytest

from apex.mcp.run_registry import (
    active_correlation_ids,
    cancel_run_by_correlation_id,
    register_run_task,
    unregister_run_task,
)


def test_register_cancel_lifecycle() -> None:
    async def main() -> None:
        async def slow() -> str:
            await asyncio.sleep(10)
            return "done"

        task = asyncio.create_task(slow())
        assert await register_run_task("t1", task) is None
        assert "t1" in active_correlation_ids()

        out = await cancel_run_by_correlation_id("t1")
        assert out["status"] == "cancel_requested"

        with pytest.raises(asyncio.CancelledError):
            await task

        await unregister_run_task("t1")
        assert "t1" not in active_correlation_ids()

    asyncio.run(main())


def test_register_rejects_duplicate() -> None:
    async def main() -> None:
        async def slow() -> None:
            await asyncio.sleep(10)

        t1 = asyncio.create_task(slow())
        assert await register_run_task("dup", t1) is None
        t2 = asyncio.create_task(slow())
        msg = await register_run_task("dup", t2)
        assert msg is not None
        t2.cancel()
        with pytest.raises(asyncio.CancelledError):
            await t2
        t1.cancel()
        with pytest.raises(asyncio.CancelledError):
            await t1
        await unregister_run_task("dup")

    asyncio.run(main())


def test_cancel_not_found() -> None:
    async def main() -> None:
        out = await cancel_run_by_correlation_id("nope")
        assert out["status"] == "not_found"

    asyncio.run(main())
