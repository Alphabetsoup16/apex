from __future__ import annotations

import asyncio

import pytest

from apex.mcp.run_registry import (
    active_correlation_ids,
    bind_correlation_task,
    cancel_run_by_correlation_id,
    reserve_correlation_slot,
    unregister_correlation,
)


def test_reserve_bind_cancel_lifecycle() -> None:
    async def main() -> None:
        async def slow() -> str:
            await asyncio.sleep(10)
            return "done"

        assert await reserve_correlation_slot("t1") is None
        assert "t1" in active_correlation_ids()

        task = asyncio.create_task(slow())
        await bind_correlation_task("t1", task)

        out = await cancel_run_by_correlation_id("t1")
        assert out["status"] == "cancel_requested"

        with pytest.raises(asyncio.CancelledError):
            await task

        await unregister_correlation("t1")
        assert "t1" not in active_correlation_ids()

    asyncio.run(main())


def test_reserve_rejects_duplicate_before_bind() -> None:
    async def main() -> None:
        assert await reserve_correlation_slot("dup") is None
        msg = await reserve_correlation_slot("dup")
        assert msg is not None
        await unregister_correlation("dup")

    asyncio.run(main())


def test_cancel_while_reserved_cancels_task_on_bind() -> None:
    async def main() -> None:
        assert await reserve_correlation_slot("early") is None
        out = await cancel_run_by_correlation_id("early")
        assert out["status"] == "cancel_requested"

        async def body() -> None:
            await asyncio.sleep(10)

        task = asyncio.create_task(body())
        await bind_correlation_task("early", task)

        with pytest.raises(asyncio.CancelledError):
            await task

        await unregister_correlation("early")

    asyncio.run(main())


def test_cancel_not_found() -> None:
    async def main() -> None:
        out = await cancel_run_by_correlation_id("nope")
        assert out["status"] == "not_found"

    asyncio.run(main())
