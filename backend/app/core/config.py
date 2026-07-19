"""Application configuration loaded from environment variables via pydantic-settings."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration for the NEX AGI backend.

    Values are read from environment variables (case-insensitive) and fall back
    to the defaults shown here for local development. In production, inject via
    a secrets manager — never commit real keys.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Runtime ──────────────────────────────────────────────────────────────
    APP_ENV: str = Field(default="local", description="local | staging | production")

    # ── Logging / observability ──────────────────────────────────────────────
    # Root log level for OUR code (app.*). Third-party chatter (openai request
    # dumps, httpx, langsmith, SQL echo) is pinned to WARNING regardless, so
    # setting DEBUG here turns up the application, not the firehose.
    LOG_LEVEL: str = Field(default="INFO", description="DEBUG | INFO | WARNING | ERROR")
    # Log every SQL statement (sqlalchemy.engine at INFO) through the normal log
    # pipeline. Prefer this over the engine's ``echo`` flag: ``echo`` installs a
    # SECOND handler on the sqlalchemy logger, printing every statement twice.
    LOG_SQL: bool = Field(default=False)

    # ── Database ─────────────────────────────────────────────────────────────
    # Async URL (asyncpg) for SQLAlchemy app tables
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://nex:nex@localhost:5433/nexagi",
    )
    # Sync psycopg URL for LangGraph PostgresSaver + PostgresStore
    LANGGRAPH_PG_URL: str = Field(
        default="postgresql://nex:nex@localhost:5433/nexagi",
    )

    # ── Redis ─────────────────────────────────────────────────────────────────
    # AG-UI event fan-out across FastAPI replicas (ARCH §24.5)
    REDIS_URL: str = Field(default="redis://localhost:6379/0")
    # Which AG-UI live fan-out backend to use (ARCH §24.5):
    #   "memory" — in-process asyncio fan-out; single replica, no Redis (default).
    #   "redis"  — cross-replica fan-out via REDIS_URL (production / multi-worker).
    STREAM_FANOUT: str = Field(default="memory", description="memory | redis")

    # ── Agents / skills (ARCH §22 / §26) ──────────────────────────────────────
    # Host directory serving filesystem **base** skills, mounted into each agent's
    # backend root (ARCH §26.3). Empty = no base skills dir (agents run without
    # filesystem skills until configured); uploaded skills are wired in Step 7.
    BASE_SKILLS_DIR: str = Field(default="")
    # Provider-AGNOSTIC resilience bound for one agent's turn (seconds), recorded as
    # a confidence-0 abstention when exceeded (§21.5) so a slow/unresponsive model —
    # on ANY provider — degrades the *one* agent instead of freezing the whole round
    # forever. Its meaning follows what is observable (see ``aagent_turn_node``):
    # with live streaming it bounds **inactivity** (time since the turn last emitted
    # a reasoning/tool event — a model actively producing work is responsive and is
    # never cancelled mid-output); non-streaming turns emit nothing until they
    # return, so there it bounds total wall-clock. Tune up for slow reasoning
    # models, down for snappier failure. This is the single resilience bound; we do
    # NOT bake a per-provider/per-model timeout anywhere else.
    AGENT_TURN_TIMEOUT_S: float = Field(default=600.0)
    # Whether the mesh agent turn streams its trajectory (``astream_events``) for
    # live reasoning/tool visibility. ON by default: without it every turn is a
    # silent multi-minute "thinking" block and the AG-UI only updates at turn end.
    # Known trade-off — some OpenAI-compatible servers (e.g. certain NVIDIA NIM /
    # vLLM builds) repeat the tool-call ``name`` across streamed delta chunks, which
    # LangChain concatenates into an invalid doubled name (``web_searchweb_search``);
    # the agent then loops on a non-existent tool under ``tool_choice=required`` and
    # never produces its ``ContributionOut``. If your provider streams tool calls
    # dirtily, set this OFF: the turn runs non-streaming (``ainvoke``), tool names
    # are parsed once and correct on every provider, and the same reasoning/tool/
    # contribution events are still emitted — projected post-hoc at turn end
    # (round-cadenced; the debate thread and edges are unaffected). This is a
    # provider-AGNOSTIC switch, not per-model logic (R3/R4).
    AGENT_LIVE_STREAMING: bool = Field(default=True)

    # ── Chat attachments (ARCH §8.5.3) ────────────────────────────────────────
    # Local object-storage root for transient chat uploads. In prod this is a
    # bucket; here it is a host directory (created on demand). Files are transient
    # per-conversation unless promoted to team knowledge.
    ATTACHMENTS_DIR: str = Field(default="var/attachments")

    # ── Knowledge files (ARCH §10.5 / §21.3) ──────────────────────────────────
    # Object-storage root for uploaded **knowledge** files (kind='file'). In prod a
    # bucket; here a host directory (created on demand). The bytes live here; the
    # knowledge_sources.uri records the location for the ingestion worker to load.
    KNOWLEDGE_FILES_DIR: str = Field(default="var/knowledge")
    # Per-knowledge-file upload cap (bytes); rejects oversized uploads at the
    # boundary (R5: validate input; fail fast). Default 50 MB.
    KNOWLEDGE_MAX_UPLOAD_BYTES: int = Field(default=50 * 1024 * 1024)
    # Per-source ingestion timeout (seconds) — a stuck loader/embed call is
    # cancelled and the source marked failed rather than hanging the worker.
    KNOWLEDGE_INGEST_TIMEOUT_S: float = Field(default=300.0)

    # ── Artifacts (ARTIFACTS.md §7/§15) ───────────────────────────────────────
    # Object-storage root for **binary** artifacts (docx/xlsx/pptx/pdf/image/zip)
    # and oversized text artifacts. In prod this is an S3/MinIO bucket behind the
    # ObjectStorage Protocol (app/artifacts/storage.py); here it is a host directory
    # (created on demand). Keys are namespaced per ``org_id`` (§7 tenancy).
    ARTIFACTS_DIR: str = Field(default="var/artifacts")
    # Hard per-artifact size cap (bytes) — rejects oversized generation at the
    # boundary (§15: size limits per artifact). Default 50 MB.
    ARTIFACT_MAX_BYTES: int = Field(default=50 * 1024 * 1024)
    # Text artifacts (markdown/code/json/csv) at or below this size inline in the
    # ``content`` column; larger ones spill to object storage (§7 "threshold
    # configurable"). Default 64 KB.
    ARTIFACT_INLINE_MAX_BYTES: int = Field(default=64 * 1024)
    # HMAC key signing short-lived download URLs (§15: signed, expiring URLs). This
    # is a SIGNING SECRET, not a provider key — inject a real random value via a
    # secrets manager in prod (R5: never ship a real secret in source). The dev
    # default only makes local links work; it is not security-bearing.
    ARTIFACT_URL_SECRET: str = Field(default="dev-artifact-signing-secret-change-me")
    # Signed download-URL lifetime (seconds). Short by design (§16: signed URLs
    # cached briefly). Default 5 minutes.
    ARTIFACT_URL_TTL_S: int = Field(default=300)

    # ── Agent capability tools (ARCH §10.5.4) ─────────────────────────────────
    # web_search capability → Tavily REST (https://api.tavily.com/search). Set the
    # key via .env / a secrets manager (R5: never hardcode a key in source) to enable
    # real search; without it the tool returns an honest "not configured" message
    # rather than silently doing nothing (R3 — no silent fakery).
    WEB_SEARCH_API_KEY: str = Field(
        default="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"
    )
    WEB_SEARCH_MAX_RESULTS: int = Field(default=5)
    # code_interpreter capability → runs model-generated Python in a subprocess.
    # OFF by default: executing generated code is a security decision the operator
    # must opt into, and the subprocess is basic isolation (timeout + temp cwd), NOT
    # a hardened sandbox (see app/tools/code_interpreter.py). Disabled → the tool
    # returns an honest "not enabled" message.
    CODE_INTERPRETER_ENABLED: bool = Field(default=True)
    CODE_INTERPRETER_TIMEOUT_S: float = Field(default=15.0)

    # ── Observability ─────────────────────────────────────────────────────────
    LANGSMITH_TRACING: bool = Field(default=False)
    LANGSMITH_API_KEY: str = Field(default="")
    LANGSMITH_PROJECT: str = Field(default="nex-agi")

    # ── Provider keys (local dev only — prod uses secrets manager) ────────────
    OPENAI_API_KEY: str = Field(default="")
    ANTHROPIC_API_KEY: str = Field(default="")

    @property
    def is_local(self) -> bool:
        return self.APP_ENV == "local"


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings singleton. Use as FastAPI dependency or direct call."""
    return Settings()
