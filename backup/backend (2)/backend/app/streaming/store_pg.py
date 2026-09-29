"""Postgres-backed ``RunEventStore`` — the durable ``run_events`` log (ARCH §24.8).

This closes the Step-8 boundary: the in-memory store (``InMemoryRunEventStore``) is
replaced by this Postgres implementation behind the **same** :class:`RunEventStore`
Protocol, so no consumer (emitter, WS endpoint) changes (the seam was designed for
exactly this swap, see ``store.py``).

RLS interaction (TECHNICAL §11.7)
---------------------------------
``run_events`` is org-scoped under FORCE RLS. Each operation opens its own short
transaction and sets ``app.current_org`` from a per-run org registered at launch
(``register_run``) — the AG-UI envelope deliberately carries no ``org_id`` (the
§24.3 contract is locked), so the org is supplied out-of-band. An operation on an
unregistered run raises rather than silently returning empty (R3): a replay that
quietly returned nothing would look like "no events" instead of a wiring bug.

Single-process scope: the registration map lives in this instance, shared via
``app.state`` by the run-launch route and the WS endpoint (same process in dev).
Cross-replica durability uses Redis fan-out for *live* events (ARCH §24.5); durable
cross-replica replay would resolve the org from the ``runs`` row via a service-role
connection — deferred with the rest of the multi-replica transport (§18).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Run, RunEvent
from app.streaming.events import AGUIEvent


class RunOrgUnknown(RuntimeError):
    """A run-event op was attempted for a run whose org was never registered."""


class PostgresRunEventStore:
    """Durable per-run event log on Postgres (implements ``RunEventStore``)."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._run_org: dict[str, UUID] = {}

    def register_run(self, run_id: str, org_id: UUID) -> None:
        """Bind a run to its org so RLS-scoped reads/writes can set ``app.current_org``."""
        self._run_org[run_id] = org_id

    async def _org_for(self, run_id: str) -> UUID:
        """Resolve a run's org for RLS, recovering from the DB on a cache miss.

        ``register_run`` populates an in-process cache at launch (the hot path), but
        that cache does not survive a restart (single-process scope; see module
        docstring). The org is **durable** on the persisted ``runs`` row, so on a
        miss we recover it from there and re-cache — this is exactly what lets a
        client reconnect and replay a run that was launched *before* the backend
        restarted (ARCH §24.8). We only raise when the run has no org anywhere
        (genuinely unknown), never as a silent empty replay (R3).
        """
        cached = self._run_org.get(run_id)
        if cached is not None:
            return cached
        recovered = await self._lookup_org(run_id)
        if recovered is None:
            raise RunOrgUnknown(f"run {run_id!r} has no registered org and none on record")
        self._run_org[run_id] = recovered
        return recovered

    async def _lookup_org(self, run_id: str) -> UUID | None:
        """Read a run's org from the durable ``runs`` row (the RLS source of truth).

        This is the deferred "resolve the org from the ``runs`` row" path the module
        docstring describes: it runs without ``app.current_org`` set, so it relies on
        a connection that can see the row (the dev superuser, or a service-role /
        BYPASSRLS connection in a future multi-replica deployment, §18).
        """
        async with self._session_factory() as session:
            org: UUID | None = await session.scalar(
                select(Run.org_id).where(Run.id == UUID(run_id))
            )
            return org

    async def _set_org(self, session: AsyncSession, org_id: UUID) -> None:
        await session.execute(
            text("SELECT set_config('app.current_org', :org, true)"), {"org": str(org_id)}
        )

    async def append(self, event: AGUIEvent) -> None:
        """Persist one AG-UI envelope as a ``run_events`` row (ordered by ``seq``)."""
        org_id = await self._org_for(event["run_id"])
        async with self._session_factory() as session:
            await self._set_org(session, org_id)
            session.add(
                RunEvent(
                    org_id=org_id,
                    run_id=UUID(event["run_id"]),
                    seq=event["seq"],
                    type=event["type"],
                    data=event["data"],
                    ts=datetime.fromisoformat(event["ts"]),
                )
            )
            await session.commit()

    async def replay(self, run_id: str, after_seq: int = 0) -> list[AGUIEvent]:
        """Return this run's events with ``seq > after_seq``, ascending (ARCH §24.8)."""
        org_id = await self._org_for(run_id)
        async with self._session_factory() as session:
            await self._set_org(session, org_id)
            # session_id is not a run_events column (§11.4); resolve it once from the
            # run so replayed envelopes carry the full §24.3 shape (faithful, not blank).
            session_id = await session.scalar(select(Run.session_id).where(Run.id == UUID(run_id)))
            rows = (
                await session.scalars(
                    select(RunEvent)
                    .where(RunEvent.run_id == UUID(run_id), RunEvent.seq > after_seq)
                    .order_by(RunEvent.seq)
                )
            ).all()
            return [self._to_envelope(r, str(session_id or "")) for r in rows]

    async def last_seq(self, run_id: str) -> int:
        """Highest persisted ``seq`` for the run, or ``0`` (resume-continuity, ARCH §24.3)."""
        org_id = await self._org_for(run_id)
        async with self._session_factory() as session:
            await self._set_org(session, org_id)
            value = await session.scalar(
                select(RunEvent.seq)
                .where(RunEvent.run_id == UUID(run_id))
                .order_by(RunEvent.seq.desc())
                .limit(1)
            )
            return value or 0

    @staticmethod
    def _to_envelope(row: RunEvent, session_id: str) -> AGUIEvent:
        """Project a ``run_events`` row back into the AG-UI envelope (§24.3)."""
        return AGUIEvent(
            type=row.type,
            session_id=session_id,
            run_id=str(row.run_id),
            seq=row.seq,
            ts=row.ts.isoformat(),
            data=row.data,
        )
