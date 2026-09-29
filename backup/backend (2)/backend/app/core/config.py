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

    # ── Rate limiting / provider pacing (ARCH R1/R2) ──────────────────────────
    # Client-side REQUESTS-per-minute budget shared by the WHOLE mesh in one run, so
    # the parallel Send() fan-out (ARCH §7) cannot burst every agent's model call into
    # the same minute and trip the provider's tokens-per-minute (TPM) / requests-per-
    # minute (RPM) limit → the 429 cascade. Implemented with LangChain's built-in
    # ``InMemoryRateLimiter`` (a real primitive, R2), which paces the number of
    # *requests*, not their token size (its documented caveat, R1-verified). Derive the
    # budget from the provider's TPM limit and your run's typical request size:
    #     requests_per_minute ≈ TPM_limit / avg_tokens_per_request
    # e.g. OpenAI tier-1 gpt-4o is 30_000 TPM; at ~6_000 tokens/request → ~5 RPM.
    # 0 (default) = pacing OFF: unchanged behaviour, relying only on the SDK's built-in
    # exponential-backoff 429 retry. NOTE: with a very low RPM and many agents, an
    # agent may wait behind the pacer long enough to matter against AGENT_TURN_TIMEOUT_S
    # — raise that bound too if you set a tight budget.
    #
    # SCALES WITH TEAM SIZE — the single most important setting for large teams. A round
    # fans out to every agent in parallel, and one ReAct turn is typically 2–4 model calls
    # (reasoning, tools, the structured exit), so a run costs roughly
    # ``agents × rounds × 3`` requests: ~45 for 5 agents × 3 rounds, ~110 for 12 agents.
    # At 5 RPM a 12-agent run spends ~20 minutes queued, agents late in a round can exceed
    # AGENT_TURN_TIMEOUT_S and abstain, and the parallel fan-out buys nothing because the
    # pacer re-serialises it. Raise this in step with team size and your provider tier
    # (roughly ``3 × agents`` RPM keeps a round flowing) or keep teams small.
    AGENT_MAX_REQUESTS_PER_MINUTE: float = Field(default=5.0)
    # Token-bucket burst: how many requests may fire back-to-back before pacing
    # throttles. Keep near 1 so the opening fan-out does not spike; raise only if your
    # provider tolerates short bursts. Ignored when pacing is OFF.
    AGENT_RATE_LIMIT_BURST: float = Field(default=1.0)
    # Per-peer contribution length cap (characters) injected into each round's prompt
    # for rounds ≥ 2 (the opening round has no peers). Truncating verbose peer
    # proposals shrinks every request, which — because the pacer meters *requests* —
    # lets more real work flow under the same budget (and cuts token cost). 0 (default)
    # = no cap (full peer content, unchanged behaviour); a value like 1500 bounds
    # runaway contributions while preserving the gist.
    AGENT_PEER_CONTENT_MAX_CHARS: int = Field(default=1500)

    # ── Run cancellation (ARCH §21.6) ─────────────────────────────────────────
    # How long a cancel waits for the run to stop COOPERATIVELY before force-cancelling
    # the task. The cooperative path stops at a checkpointed boundary and keeps the work
    # done so far; a forced cancel discards everything since the last node boundary and can
    # leave an inner model call running. So this should comfortably exceed a typical turn's
    # remaining time — but stay short enough that a stuck run still stops promptly.
    RUN_CANCEL_GRACE_S: float = Field(default=20.0)
    # How often the graph re-reads ``runs.status`` to notice a cancel issued on ANOTHER
    # replica. The in-process flag is instant, so this only bounds the cross-replica case;
    # one small query per node boundary is negligible beside a model call.
    RUN_CANCEL_POLL_S: float = Field(default=5.0)

    # ── A2A inter-agent messaging (ARCH §23.5 anti-chaos limits) ──────────────
    # These bound an inherently O(N²) channel: N agents may address N peers every round,
    # and every message becomes tokens in someone else's prompt next round. Left
    # unbounded, a 5-agent × 3-round run can generate more coordination chatter than
    # actual work — the classic message storm.
    #
    # Max messages ONE agent may emit in ONE turn. Over budget, the lowest-priority
    # messages are dropped (VOTE/ENDORSE/CRITIQUE outrank REQUEST/DELEGATE, which outrank
    # PROPOSE/INFORM) with a recorded warning — never silently. 0 = no cap.
    A2A_MAX_MESSAGES_PER_TURN: int = Field(default=4)
    # How many DELEGATE hops a piece of work may travel. A hand-off chain with no bound is
    # a known production failure: A delegates to B, B to C, C back to A, and the round
    # budget is spent passing work around instead of doing it.
    A2A_MAX_DELEGATION_DEPTH: int = Field(default=2)
    # ── Inbox rendering budget (§23.5 context trimming) ───────────────────────
    # What lands in an agent's next-round prompt. Bounded as a TOTAL budget rather than a
    # uniform per-message cap, because the intents have wildly different sizes: a VOTE
    # carries no body at all, while an INFORM exists precisely to carry substance ("the 3
    # regulations I found, tagged so Compliance can cite them"). A flat cap spends the same
    # allowance on both — starving the message that matters to pad the one that doesn't.
    #
    # Messages are rendered in §23.5 priority order until the total budget is spent; what
    # does not fit is listed as a visible header ("[not shown — inbox full]"), never
    # dropped invisibly. A half-read REQUEST is worse than a clearly-marked unread one.
    #
    # Total characters of message bodies per agent per round. ~4 chars/token ⇒ 4000 ≈ 1000
    # tokens, deliberately kept at or below the peer-contributions block it sits beside
    # (N peers × AGENT_PEER_CONTENT_MAX_CHARS). 0 = no total cap.
    A2A_INBOX_MAX_CHARS: int = Field(default=4000)
    # Ceiling for any SINGLE message body, so one verbose peer cannot consume the whole
    # inbox. Set to parity with AGENT_PEER_CONTENT_MAX_CHARS: a peer's message should not
    # be squeezed harder than a peer's contribution. 0 = no per-message cap.
    A2A_MESSAGE_MAX_CHARS: int = Field(default=1500)
    # Hard bound on inbox length regardless of size, so 40 one-line VOTEs cannot bury a
    # DELEGATE. Applied after priority ordering.
    A2A_INBOX_MAX_MESSAGES: int = Field(default=12)

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
    # NEVER a real key in source (R5). Supply via .env / a secrets manager; empty
    # means the tool reports "not configured" rather than silently doing nothing.
    WEB_SEARCH_API_KEY: str = Field(default="")
    WEB_SEARCH_MAX_RESULTS: int = Field(default=5)
    # code_interpreter capability → runs model-generated Python in a subprocess.
    # OFF by default: executing generated code is a security decision the operator
    # must opt into, and the subprocess is basic isolation (timeout + temp cwd), NOT
    # a hardened sandbox (see app/tools/code_interpreter.py). Disabled → the tool
    # returns an honest "not enabled" message.
    CODE_INTERPRETER_ENABLED: bool = Field(default=False)
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
