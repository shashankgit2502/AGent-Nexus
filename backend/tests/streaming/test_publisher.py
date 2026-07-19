"""Tests for live event fan-out (ARCH §24.5).

The in-process publisher is fully tested. The Redis publisher is exercised only
when a Redis is reachable (``docker compose up``), mirroring the ``requires_postgres``
pattern in ``tests/graph/test_build.py`` — no network dependency for the default
test run.
"""

from __future__ import annotations

import asyncio

import pytest

from app.streaming.events import AGUIEvent, build_event
from app.streaming.publisher import InProcessEventPublisher, channel_for


def _event(run_id: str, seq: int) -> AGUIEvent:
    return build_event({"type": "contribution"}, session_id="s", run_id=run_id, seq=seq)


def test_channel_name_follows_arch_convention() -> None:
    assert channel_for("abc") == "run:abc"


async def test_in_process_delivers_to_subscriber() -> None:
    pub = InProcessEventPublisher()
    received: list[AGUIEvent] = []

    async def consume() -> None:
        async for event in pub.subscribe("r"):
            received.append(event)
            return  # one event is enough

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.01)  # let the subscriber register its queue
    await pub.publish(_event("r", 1))
    await asyncio.wait_for(task, timeout=1.0)

    assert [e["seq"] for e in received] == [1]


async def test_in_process_only_delivers_matching_run() -> None:
    pub = InProcessEventPublisher()
    received: list[AGUIEvent] = []

    async def consume() -> None:
        async for event in pub.subscribe("r1"):
            received.append(event)
            return

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.01)
    await pub.publish(_event("other-run", 1))  # different run → ignored
    await pub.publish(_event("r1", 1))
    await asyncio.wait_for(task, timeout=1.0)

    assert [e["run_id"] for e in received] == ["r1"]


async def test_subscriber_deregisters_on_close() -> None:
    """Closing the subscription runs the generator's finally → no leaked queue.

    Note on async-generator semantics: merely breaking/returning out of
    ``async for`` does *not* synchronously run the generator's ``finally`` — that
    happens on ``aclose()`` (or GC). The WebSocket handler triggers this when the
    socket closes and the iteration unwinds; here we call ``aclose()`` explicitly
    to assert the cleanup deterministically.
    """
    pub = InProcessEventPublisher()
    gen = pub.subscribe("r")

    # Prime the generator so its queue registers, then deliver one event.
    first = asyncio.ensure_future(gen.__anext__())
    await asyncio.sleep(0.01)
    assert "r" in pub._subscribers  # noqa: SLF001 — white-box: registered while live
    await pub.publish(_event("r", 1))
    event = await asyncio.wait_for(first, timeout=1.0)
    assert event["seq"] == 1

    await gen.aclose()  # runs the generator's finally
    assert "r" not in pub._subscribers  # noqa: SLF001 — white-box: cleaned up


# ── Redis backend (only when reachable) ──────────────────────────────────────


def _redis_available() -> bool:
    try:
        import redis as sync_redis

        client = sync_redis.Redis.from_url("redis://localhost:6379/0", socket_connect_timeout=2)
        client.ping()
        client.close()
        return True
    except Exception:  # noqa: BLE001 — availability probe; any failure = skip
        return False


requires_redis = pytest.mark.skipif(not _redis_available(), reason="Redis not reachable")


@requires_redis
async def test_redis_publish_subscribe_roundtrip() -> None:
    from redis.asyncio import Redis

    from app.streaming.publisher import RedisEventPublisher

    client = Redis.from_url("redis://localhost:6379/0")
    pub = RedisEventPublisher(client)
    received: list[AGUIEvent] = []

    async def consume() -> None:
        async for event in pub.subscribe("r-redis"):
            received.append(event)
            return

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.1)  # allow the SUBSCRIBE to register on the server
    await pub.publish(_event("r-redis", 1))
    await asyncio.wait_for(task, timeout=2.0)
    await client.aclose()

    assert [e["seq"] for e in received] == [1]
