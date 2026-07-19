"""FastAPI application factory and lifespan.

Lifespan responsibilities (TECHNICAL §3.2, BUILD_PLAYBOOK Step 1):
  1. Configure structured logging.
  2. Set up LangGraph PostgresSaver tables (checkpointer — short-term memory / HITL resume).
  3. Set up LangGraph PostgresStore tables (long-term per-agent memory, pgvector-indexed).
  4. Hold the live checkpointer + store open for the full app lifetime and expose them via
     app.state for dependency injection (see core/deps.py).

Import paths (R1-verified via LangChain docs MCP 2025-06-17):
  from langgraph.checkpoint.postgres import PostgresSaver
  from langgraph.store.postgres import PostgresStore

Lifecycle pattern: nested `with` blocks spanning the `yield` keep the psycopg
connections open for the entire app lifetime. Connections are opened/closed only
at startup/shutdown (brief, blocking is acceptable). The `with` blocks correctly
type the bound variables as PostgresSaver / PostgresStore via __enter__ return types.
"""

import asyncio
import logging
import sys
from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi.middleware.cors import CORSMiddleware

# Windows: psycopg's async mode (AsyncPostgresSaver/Store) cannot run on the default
# ProactorEventLoop — it requires a SelectorEventLoop. Set the policy at import, before
# uvicorn/pytest create their loop. asyncpg (our SQLAlchemy engine) works on both, so
# this is safe; on non-Windows it is a no-op. (R1: psycopg InterfaceError documents this.)
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres import PostgresStore
from langgraph.store.postgres.aio import AsyncPostgresStore

from app.api import (
    agents,
    artifacts,
    conversations,
    knowledge,
    memory,
    providers,
    sessions,
    stats,
    teams,
)
from app.core.config import Settings, get_settings
from app.core.identity import seed_default_organization
from app.core.logging import configure_logging
from app.db.session import AsyncSessionLocal, engine
from app.knowledge.worker import recover_stuck_sources
from app.streaming import (
    EventPublisher,
    InProcessEventPublisher,
    RedisEventPublisher,
    RunEventStore,
    build_stream_router,
)
from app.streaming.run_recovery import recover_orphaned_runs
from app.streaming.store_pg import PostgresRunEventStore

logger = logging.getLogger(__name__)


def _build_event_publisher(settings: Settings) -> EventPublisher:
    """Select the AG-UI live fan-out backend (ARCH §24.5).

    ``memory`` (default) needs no Redis — correct for single-replica dev. ``redis``
    fans events across replicas via ``redis.asyncio``. The Redis client is created
    lazily here so importing the app never requires a running Redis.
    """
    if settings.STREAM_FANOUT == "redis":
        from redis.asyncio import Redis  # local import: only needed for the redis backend

        return RedisEventPublisher(Redis.from_url(settings.REDIS_URL))
    return InProcessEventPublisher()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application start-up and shut-down sequence.

    The collaboration graph is driven with ``graph.astream`` (the run-launch route),
    so it needs **async** persistence: ``AsyncPostgresSaver`` + ``AsyncPostgresStore``
    (R1-verified import paths under ``.aio``). A small **sync** ``PostgresStore`` is
    also opened for the memory-read endpoint, whose Step-7 ``MemoryService`` is
    synchronous; both operate over the same idempotently-created ``store`` table.
    The ``AsyncExitStack`` keeps all three connections open for the app lifetime and
    closes them cleanly on shutdown.
    """
    settings = get_settings()
    configure_logging(settings.APP_ENV, level=settings.LOG_LEVEL, log_sql=settings.LOG_SQL)

    logger.info("NEX AGI backend starting (env=%s)", settings.APP_ENV)
    pg_url = settings.LANGGRAPH_PG_URL

    async with AsyncExitStack() as stack:
        checkpointer = await stack.enter_async_context(AsyncPostgresSaver.from_conn_string(pg_url))
        await checkpointer.setup()  # CREATE TABLE IF NOT EXISTS — async checkpointer schema
        store = await stack.enter_async_context(AsyncPostgresStore.from_conn_string(pg_url))
        await store.setup()  # async long-term memory / pgvector schema
        # Sync store for the synchronous MemoryService-backed memory endpoint.
        memory_store = stack.enter_context(PostgresStore.from_conn_string(pg_url))
        memory_store.setup()

        app.state.checkpointer = checkpointer
        app.state.store = store
        app.state.memory_store = memory_store

        # Seed the dev default organization and expose its id for the
        # org-context dependency (app.core.identity). Idempotent.
        async with AsyncSessionLocal() as session:
            app.state.default_org_id = await seed_default_organization(session)
            await session.commit()

        # Durability: re-enqueue any knowledge sources left mid-ingestion by a
        # crash/restart (ITEM 2 — the status column is the job state). Best-effort:
        # a recovery failure must not block startup, but it is logged, not swallowed.
        try:
            await recover_stuck_sources(app)
        except Exception:  # noqa: BLE001 — startup must proceed; failure is logged
            logger.warning("knowledge: stuck-source recovery failed on startup", exc_info=True)

        # Durability: finalize any runs left `running` by a crash/restart (ARCH
        # §24.8). The driving asyncio task died with the previous process, so the
        # run would otherwise stay `running` forever and a reconnecting client's
        # AG-UI stream would hang on "thinking" with no terminal event. Same
        # best-effort contract as the ingestion recovery above.
        try:
            await recover_orphaned_runs(app)
        except Exception:  # noqa: BLE001 — startup must proceed; failure is logged
            logger.warning("run-recovery: orphaned-run recovery failed on startup", exc_info=True)

        logger.info(
            "LangGraph async checkpointer + store ready; default_org=%s; AG-UI fan-out=%s",
            app.state.default_org_id,
            settings.STREAM_FANOUT,
        )
        try:
            yield  # ← application serves requests here
        finally:
            # Await any in-flight background run + ingestion tasks (ARCH §24.5) so the
            # graph and the knowledge worker finish persisting before connections close
            # — required for clean teardown under TestClient and correct in prod.
            pending = list(getattr(app.state, "run_tasks", ())) + list(
                getattr(app.state, "ingest_tasks", ())
            )
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            # Dispose the async engine's connection pool on shutdown so asyncpg
            # connections are released while their event loop is still alive
            # (required for clean teardown under TestClient, and correct in prod).
            await engine.dispose()

    logger.info("NEX AGI backend shut down")


def create_app() -> FastAPI:
    """Build and return the FastAPI application instance."""
    settings = get_settings()

    application = FastAPI(
        title="NEX AGI",
        description="Decentralized multi-agent operating system",
        version="0.1.0",
        docs_url="/docs" if settings.is_local else None,
        redoc_url="/redoc" if settings.is_local else None,
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        # allow_origins=settings.CORS_ORIGINS,  # see note below
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # AG-UI streaming collaborators (ARCH §24), constructed at app build time so the
    # WS endpoint can close over them. The durable run-event log (replay, §24.8)
    # and the live fan-out publisher (§24.5) are exposed on app.state so the
    # run-launch route shares the same instances. Step 9 closed the Step-8 boundary:
    # the Postgres-backed `run_events` store now replaces the in-memory one behind
    # the same `RunEventStore` Protocol (no consumer edits).
    event_store: RunEventStore = PostgresRunEventStore(AsyncSessionLocal)
    event_publisher = _build_event_publisher(settings)
    application.state.event_store = event_store
    application.state.event_publisher = event_publisher
    # Strong refs to in-flight background run tasks (ARCH §24.5); see spawn_run.
    application.state.run_tasks = set()
    # Strong refs to in-flight knowledge-ingestion tasks (ITEM 2); see spawn_ingestion.
    application.state.ingest_tasks = set()

    @application.get("/health", tags=["infra"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    # AG-UI event stream: WS /sessions/{id}/stream (ARCH §24.2). The run-launch
    # REST route that *drives* a run lands in Step 9.
    application.include_router(
        build_stream_router(event_store, event_publisher), tags=["streaming"]
    )

    # REST CRUD + collaboration routers (ARCH §14, BUILD_PLAYBOOK Step 9). Each
    # router declares its own full paths (so nested resources like
    # /teams/{id}/agents stay cohesive) and is org-scoped via the get_db dependency.
    for module in (
        teams,
        agents,
        sessions,
        providers,
        knowledge,
        memory,
        conversations,
        artifacts,
        stats,
    ):
        application.include_router(module.router)

    return application


app = create_app()
