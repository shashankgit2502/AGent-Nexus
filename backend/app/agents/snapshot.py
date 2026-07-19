"""Run-time config snapshot → MeshContext (ARCH §22, composition root for Step 9).

The Step 3/4 domain repositories (``AgentRepository``/``ConnectionRepository``/…)
are **synchronous** Protocols consumed *inside* the graph, while the API/DB layer is
async. So at launch we load a consistent **snapshot** of the team's agents and the
org's model layer from Postgres (async), populate the existing in-memory domain
repositories with it, and hand those to the real :class:`FactoryMeshRunner` /
:class:`ModelResolver` / :class:`LLMSynthesizer`. No DB I/O happens inside the
synchronous agent turn, and the locked DI design (``MeshContext``) is unchanged.

Both-paths policy (user-confirmed, revised): viability is decided **per agent**, not
all-or-nothing. An agent is *viable* when its model resolves under the §9.3
tool-calling gate and its secret is available. As long as **at least one** agent is
viable we build a real :class:`MeshContext`; the viable agents run real ReAct turns
while each non-viable agent degrades to a per-agent confidence-0 **abstention** at
runtime (§21.5) carrying an actionable reason (surfaced as an AG-UI ``error`` event),
rather than one misconfigured agent collapsing the whole team to the stub. Only a team
with **zero** viable agents falls back to the deterministic **stub** path
(``context=None``), which still lets a keys-free run be launched end-to-end.

Why an abstention and not a knowledge-only answer: every agent's output contract is a
tool call (``ToolStrategy(ContributionOut)``, see :mod:`app.agents.factory`), so a
non-tool-capable model cannot emit a contribution at all — and an agent silently
answering from parametric memory instead of its tools would ship ungrounded output
(dangerous for document-grounded roles). The §9.3 gate is locked precisely to prevent
that; we honour it and fail the *one* agent honestly.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path
from uuid import UUID

from langchain_core.tools import BaseTool
from langchain_core.vectorstores import VectorStore
from langgraph.store.base import BaseStore
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.config import AgentConfig, Capabilities, InMemoryAgentRepository
from app.agents.factory import AgentFactory, ModelProvider
from app.agents.mesh import FactoryMeshRunner
from app.artifacts.producer import ArtifactAgentProducer
from app.artifacts.service import ArtifactService
from app.artifacts.storage import build_storage
from app.core.config import Settings
from app.core.secrets import build_secret_resolver
from app.db.models import Agent as AgentRow
from app.db.models import InferenceProfile as ProfileRow
from app.db.models import KnowledgeSource as KnowledgeSourceRow
from app.db.models import LLMConnection as ConnRow
from app.db.models import ModelCatalog as CatalogRow
from app.graph.context import EmitFn, MeshContext
from app.knowledge.embedding_selection import resolve_embedding_model_id
from app.knowledge.retriever import make_conversation_tool, make_rag_tool_builder
from app.knowledge.store import (
    build_knowledge_vectorstore,
    knowledge_collection_name,
    knowledge_connection_url,
)
from app.memory.consolidation import MemoryConsolidator
from app.memory.items import MemoryItemStore
from app.memory.service import MemoryService
from app.models_layer.catalog import CatalogModel, InMemoryCatalogRepository
from app.models_layer.connections import InMemoryConnectionRepository, LLMConnection
from app.models_layer.embeddings import EmbeddingsResolver
from app.models_layer.errors import ModelResolutionError
from app.models_layer.profiles import InferenceProfile, InMemoryProfileRepository
from app.models_layer.resolver import ModelResolver
from app.synthesis.synthesizer import LLMSynthesizer
from app.tools.code_interpreter import make_code_interpreter_tool
from app.tools.registry import ToolRegistry
from app.tools.web_search import make_web_search_tool

logger = logging.getLogger(__name__)


async def load_active_agent_ids(session: AsyncSession, *, org_id: UUID, team_id: UUID) -> list[str]:
    """Return the team's live agent ids as strings (the mesh roster, both paths)."""
    rows = (
        await session.scalars(
            select(AgentRow.id).where(
                AgentRow.org_id == org_id,
                AgentRow.team_id == team_id,
                AgentRow.deleted_at.is_(None),
            )
        )
    ).all()
    return [str(r) for r in rows]


# Actionable hint appended to every "degraded to stub" / "agent will abstain" log so
# the cause is fixable from the message alone (R3 — don't bury the reason).
_VIABILITY_HINT = (
    "Check that the agent has an inference profile whose model has supports_tools=true "
    "and a resolvable API key (the §9.3 tool-calling gate is a locked decision)."
)


def partition_viable_agents(
    configs: Sequence[AgentConfig], resolver: ModelProvider
) -> tuple[list[AgentConfig], dict[str, str]]:
    """Split a team's agents into real-mesh-viable vs must-abstain (§9.3, per-agent).

    An agent is *viable* when :meth:`ModelResolver.resolve` succeeds under the
    tool-calling hard gate (``require_tools=True``) — i.e. its model is tool-capable,
    its connection is enabled, and its secret resolves. Resolving also warms the
    resolver cache the runtime reuses.

    A non-viable agent is **not** a reason to collapse the whole team to the stub path
    (the prior all-or-nothing policy): it is recorded here with an actionable reason and
    degrades to a per-agent abstention at runtime (§21.5), while its viable peers run for
    real. Only a team with zero viable agents falls back to the stub.

    Returns:
        ``(viable, nonviable)`` where ``viable`` preserves input order and
        ``nonviable`` maps ``str(agent_id) → human-readable reason``.
    """
    viable: list[AgentConfig] = []
    nonviable: dict[str, str] = {}
    for cfg in configs:
        try:
            resolver.resolve(cfg.model_ref(), require_tools=True)
            viable.append(cfg)
        except Exception as exc:  # noqa: BLE001 — per-agent graceful degradation (§21.5).
            # Any resolution failure (non-tool model, disabled connection, missing
            # secret/SecretNotFound, unknown id) makes THIS agent abstain — not the
            # team go stub. Recorded + surfaced by the caller, never silently swallowed.
            nonviable[str(cfg.id)] = str(exc)
    return viable, nonviable


async def build_mesh_context(
    session: AsyncSession,
    *,
    org_id: UUID,
    team_id: UUID,
    store: BaseStore,
    settings: Settings,
    conversation_id: UUID | None = None,
    emit: EmitFn | None = None,
    run_id: UUID | None = None,
) -> MeshContext | None:
    """Assemble a real :class:`MeshContext`, or ``None`` to select the stub path.

    Returns ``None`` (never raises) when the real path is not viable, so launch is
    resilient: an unconfigured team still produces a runnable, observable run.

    ``conversation_id`` (chat run-per-turn, §8.5.2) enables the per-turn
    conversation-attachment retriever: if the conversation has ingested transient
    uploads, every agent gets a ``search_uploaded_files`` tool for this run (§8.5.3).

    ``emit`` (the run's event sink) enables **live** activity streaming (Bug 5): the
    mesh node streams each agent's reasoning / tool calls through it as they happen.

    ``run_id`` (real runs) enables the post-consensus **artifact producer** (ARTIFACTS
    §2A): when the team has a file-capable agent (``doc_chart`` capability), a single
    designated producer agent is wired to emit downloadable files from the consensus
    result. Omitted (or no producer-capable agent) ⇒ prose-only runs.
    """
    try:
        configs = await _load_agent_configs(session, org_id=org_id, team_id=team_id)
        if not configs:
            return None
        resolver = await _build_resolver(session, org_id=org_id, settings=settings)

        # Pre-flight (per-agent, §9.3): partition the roster into agents that can run a
        # real ReAct turn vs agents that must abstain. A single non-viable agent no
        # longer collapses the team to the stub — it abstains at runtime while its
        # viable peers run for real (see module docstring).
        viable, nonviable = partition_viable_agents(configs, resolver)
        for agent_id, reason in nonviable.items():
            logger.warning(
                "Agent %s will ABSTAIN this run (not viable for a real ReAct turn): %s. %s",
                agent_id,
                reason,
                _VIABILITY_HINT,
            )
        if not viable:
            logger.warning(
                "Team %s: 0 of %d agents are viable for a real mesh → STUB path "
                "(all agents will return placeholder proposals). %s",
                team_id,
                len(configs),
                _VIABILITY_HINT,
            )
            return None
        # The synthesizer may use a cheaper non-tool model (locked decision), but resolve
        # it from a VIABLE agent so one misconfigured agent never breaks synthesis either.
        synth_model = resolver.resolve(viable[0].model_ref(), require_tools=False)

        base_dir = Path(settings.BASE_SKILLS_DIR) if settings.BASE_SKILLS_DIR else None
        registry, extra_tools = await _build_retrieval_tools(
            session,
            org_id=org_id,
            team_id=team_id,
            settings=settings,
            configs=configs,
            conversation_id=conversation_id,
        )
        factory = AgentFactory(
            models=resolver,
            tools=registry,
            store=store,
            base_skills_dir=base_dir,
            extra_tools=extra_tools,
        )
        runner = FactoryMeshRunner(factory=factory, repo=InMemoryAgentRepository(configs))
        # Post-consensus artifact producer (ARTIFACTS §2A): the single designated
        # producer is the first VIABLE agent with the doc_chart capability (§13 gate).
        # No such agent ⇒ no producer (prose-only run); no run_id (foundation tests) ⇒
        # no producer either, since persistence is run-scoped.
        producer = _build_producer(
            viable,
            resolver=resolver,
            session=session,
            org_id=org_id,
            settings=settings,
            run_id=run_id,
        )
        # Post-run memory write trigger (Item 3 M2): consolidation reuses the cheap
        # synthesizer model and the same long-term store the agents read, so a
        # memory-enabled agent's learnings are persisted and recalled next session.
        consolidator = MemoryConsolidator(
            configs=configs,
            items=MemoryItemStore(store),
            service=MemoryService(store),
            model=synth_model,
        )
        return MeshContext(
            runner=runner,
            synthesizer=LLMSynthesizer(model=synth_model),
            consolidator=consolidator,
            producer=producer,
            emit=emit,
            turn_timeout_s=settings.AGENT_TURN_TIMEOUT_S,
            live_streaming=settings.AGENT_LIVE_STREAMING,
        )
    except Exception as exc:  # noqa: BLE001 — any unexpected wiring gap → deterministic stub.
        # Resilient fallback, but NOT silent. Per-agent model-resolution failures are now
        # handled inside ``partition_viable_agents`` (an agent abstains, the team does not
        # go stub); this outer guard only fires on a team-wide wiring gap that no per-agent
        # path can absorb — e.g. a NULL-profile agent (``_SnapshotIncomplete``), or the
        # knowledge/embedding store wiring raising. Logged at WARNING with the concrete
        # reason so a quiet degradation to placeholder proposals is still diagnosable (R3).
        logger.warning(
            "Team %s falling back to the STUB mesh (agents will return placeholder "
            "proposals): %s: %s. %s",
            team_id,
            type(exc).__name__,
            exc,
            _VIABILITY_HINT,
        )
        return None


def _build_producer(
    viable: Sequence[AgentConfig],
    *,
    resolver: ModelResolver,
    session: AsyncSession,
    org_id: UUID,
    settings: Settings,
    run_id: UUID | None,
) -> ArtifactAgentProducer | None:
    """Build the post-consensus artifact producer, or ``None`` (ARTIFACTS §2A / §13).

    The designated producer is the first **viable** agent with a file-producing
    capability — ``doc_chart`` ("Create documents/charts/code") or ``image_gen``
    ("Create images"), the §13 gate. Its already-viable (tool-capable) model is reused
    with ``require_tools=True`` — the producer must call the artifact tools; the tools
    it is granted are assembled from those capabilities. Returns ``None`` when there is
    no producer-capable agent or no ``run_id`` (artifacts are run-scoped) → prose-only.
    """
    if run_id is None:
        return None
    producer_cfg = next(
        (c for c in viable if c.capabilities.doc_chart or c.capabilities.image_gen), None
    )
    if producer_cfg is None:
        return None
    model = resolver.resolve(producer_cfg.model_ref(), require_tools=True)
    service = ArtifactService(
        session, build_storage(settings.ARTIFACTS_DIR), settings, org_id
    )
    logger.info(
        "artifact producer wired: agent %s is the designated producer for run %s",
        producer_cfg.id,
        run_id,
    )
    return ArtifactAgentProducer(
        model=model,
        service=service,
        run_id=run_id,
        producer_agent_id=producer_cfg.id,
        doc_chart=producer_cfg.capabilities.doc_chart,
        image_gen=producer_cfg.capabilities.image_gen,
    )


async def _load_agent_configs(
    session: AsyncSession, *, org_id: UUID, team_id: UUID
) -> list[AgentConfig]:
    """Map the team's agent rows into spawn-time :class:`AgentConfig` objects."""
    rows = (
        await session.scalars(
            select(AgentRow).where(
                AgentRow.org_id == org_id,
                AgentRow.team_id == team_id,
                AgentRow.deleted_at.is_(None),
            )
        )
    ).all()
    configs: list[AgentConfig] = []
    for a in rows:
        if a.profile_id is None:
            # No inference profile → cannot resolve a model for a real run.
            raise _SnapshotIncomplete(f"agent {a.id} has no inference profile")
        caps = {k: v for k, v in (a.capabilities or {}).items() if k in Capabilities.model_fields}
        configs.append(
            AgentConfig(
                id=a.id,
                org_id=a.org_id,
                team_id=a.team_id,
                name=a.name,
                description=a.description,
                instructions=a.instructions or "",
                capabilities=Capabilities(**caps),
                memory_enabled=a.memory_enabled,
                profile_id=a.profile_id,
                override_model_id=a.override_model_id,
            )
        )
    return configs


async def build_org_resolver(
    session: AsyncSession, *, org_id: UUID, settings: Settings
) -> ModelResolver:
    """Public entry: a :class:`ModelResolver` over the org's model layer (ARCH §9).

    Used by the no-team chat path (ARCH §8.5) to resolve the conversation's chosen
    model for a single ``create_agent``; shares the exact resolution the mesh uses.
    """
    return await _build_resolver(session, org_id=org_id, settings=settings)


async def _load_conn_cat_repos(
    session: AsyncSession, *, org_id: UUID
) -> tuple[InMemoryConnectionRepository, InMemoryCatalogRepository]:
    """Load the org's connection + catalog rows into in-memory domain repos.

    Shared by the chat/mesh :class:`ModelResolver` and the knowledge
    :class:`EmbeddingsResolver` so both read the *same* Connection→Catalog snapshot
    (one query path, no drift between what a model resolves to and what an embedding
    resolves to).
    """
    conns = (
        await session.scalars(
            select(ConnRow).where(ConnRow.org_id == org_id, ConnRow.deleted_at.is_(None))
        )
    ).all()
    cats = (
        await session.scalars(
            select(CatalogRow).where(CatalogRow.org_id == org_id, CatalogRow.deleted_at.is_(None))
        )
    ).all()
    conn_repo = InMemoryConnectionRepository(
        [
            LLMConnection(
                id=c.id,
                display_name=c.display_name,
                provider=c.provider,
                base_url=c.base_url,
                api_key_ref=c.api_key_ref,
                api_version=c.api_version,
                enabled=c.enabled,
                validated_at=c.validated_at,
            )
            for c in conns
        ]
    )
    cat_repo = InMemoryCatalogRepository(
        [
            CatalogModel(
                id=m.id,
                provider_connection_id=m.provider_connection_id,
                display_name=m.display_name,
                model_identifier=m.model_identifier,
                model_type=m.model_type,
                deployment_name=m.deployment_name,
                supports_tools=m.supports_tools,
                supports_streaming=m.supports_streaming,
                supports_vision=m.supports_vision,
                supports_reasoning=m.supports_reasoning,
                context_window=m.context_window,
                enabled=m.enabled,
            )
            for m in cats
        ]
    )
    return conn_repo, cat_repo


async def _build_resolver(
    session: AsyncSession, *, org_id: UUID, settings: Settings
) -> ModelResolver:
    """Populate in-memory domain repos from the org's model layer and build the resolver."""
    conn_repo, cat_repo = await _load_conn_cat_repos(session, org_id=org_id)
    profs = (
        await session.scalars(
            select(ProfileRow).where(ProfileRow.org_id == org_id, ProfileRow.deleted_at.is_(None))
        )
    ).all()
    prof_repo = InMemoryProfileRepository(
        [
            InferenceProfile(
                id=p.id,
                name=p.name,
                default_model_id=p.default_model_id,
                temperature=p.temperature,
                top_p=p.top_p,
                max_tokens=p.max_tokens,
                reasoning_level=p.reasoning_level,
                json_mode=p.json_mode,
            )
            for p in profs
        ]
    )
    # Shared factory: env-ref overrides for the first-class keys + local-dev raw-key
    # support (Bug 5). Single source of truth for the secret-resolution policy.
    secrets = build_secret_resolver(settings)
    return ModelResolver(
        connections=conn_repo, catalog=cat_repo, profiles=prof_repo, secrets=secrets
    )


async def _build_retrieval_tools(
    session: AsyncSession,
    *,
    org_id: UUID,
    team_id: UUID,
    settings: Settings,
    configs: list[AgentConfig],
    conversation_id: UUID | None,
) -> tuple[ToolRegistry, tuple[BaseTool, ...]]:
    """Assemble the run's capability tools: the registry + per-turn extra tools.

    Registered capability tools (§10.5.4):

    * **web_search** / **code_interpreter** — settings-driven tools (Bug 5 Part A),
      registered unconditionally so an agent that enables either can actually call it
      (real when its key/flag is configured, else an honest "not configured" tool).
    * **RAG** (``search_knowledge``, §10.5.2) — needs the team's embedding-model vector
      store; registered only when some agent enables ``rag`` (Bug 1).
    * **Conversation attachments** (``search_uploaded_files``, §8.5.3) — a per-turn
      extra tool added to every agent when the chat conversation has ingested uploads
      (Bug 2). Independent of RAG capability: any agent must be able to read a file the
      user just attached.

    The embedding store is built once (same per-embedding-model collection ingestion
    wrote to) and shared by RAG + attachments. Never collapses the mesh: a missing
    store just means RAG/attachments are unavailable (logged).
    """
    registry = ToolRegistry()
    # Settings-driven capability tools — no DB/embedding needed, so always available.
    web_search_tool = make_web_search_tool(settings)
    code_tool = make_code_interpreter_tool(settings)
    registry.register("web_search", lambda _cfg: [web_search_tool])
    registry.register("code_interpreter", lambda _cfg: [code_tool])

    needs_rag = any(cfg.capabilities.rag for cfg in configs)
    has_attachments = conversation_id is not None and await _conversation_has_ready_sources(
        session, org_id=org_id, conversation_id=conversation_id
    )
    if not needs_rag and not has_attachments:
        return registry, ()

    vector_store = await _build_embedding_vectorstore(
        session, org_id=org_id, team_id=team_id, settings=settings
    )
    if vector_store is None:
        return registry, ()

    if needs_rag:
        registry.register("rag", make_rag_tool_builder(vector_store))
    extra_tools: tuple[BaseTool, ...] = ()
    if has_attachments and conversation_id is not None:
        extra_tools = (
            make_conversation_tool(vector_store, org_id=org_id, conversation_id=conversation_id),
        )
    return registry, extra_tools


async def build_conversation_attachment_tool(
    session: AsyncSession,
    *,
    org_id: UUID,
    team_id: UUID | None,
    conversation_id: UUID,
    settings: Settings,
) -> BaseTool | None:
    """The per-turn ``search_uploaded_files`` tool, or ``None`` if not applicable (§8.5.3).

    Public entry shared by the no-team chat path (:mod:`app.chat.single_agent`); the
    team mesh builds the same tool inline (reusing its RAG vector store). Returns
    ``None`` when the conversation has no ingested uploads or the embedding store can't
    be built — the turn simply runs without the attachment tool.
    """
    if not await _conversation_has_ready_sources(
        session, org_id=org_id, conversation_id=conversation_id
    ):
        return None
    vector_store = await _build_embedding_vectorstore(
        session, org_id=org_id, team_id=team_id, settings=settings
    )
    if vector_store is None:
        return None
    return make_conversation_tool(vector_store, org_id=org_id, conversation_id=conversation_id)


async def _conversation_has_ready_sources(
    session: AsyncSession, *, org_id: UUID, conversation_id: UUID
) -> bool:
    """True if the conversation has at least one fully-ingested transient upload (§8.5.3)."""
    found = await session.scalar(
        select(KnowledgeSourceRow.id)
        .where(
            KnowledgeSourceRow.org_id == org_id,
            KnowledgeSourceRow.conversation_id == conversation_id,
            KnowledgeSourceRow.status == "ready",
            KnowledgeSourceRow.deleted_at.is_(None),
        )
        .limit(1)
    )
    return found is not None


async def _build_embedding_vectorstore(
    session: AsyncSession, *, org_id: UUID, team_id: UUID | None, settings: Settings
) -> VectorStore | None:
    """Build the ``PGVector`` store for the team/org embedding model, or ``None``.

    Retrieval MUST hit the *same* per-embedding-model collection ingestion wrote to —
    collections are split by embedding model (§9.5 / :func:`knowledge_collection_name`),
    since pgvector column dimension is fixed per model — so we resolve the embedding
    model with the **same** chain the ingest worker uses (team → org default; ``team_id``
    may be ``None`` for a no-team conversation) and point ``PGVector`` at the matching
    collection. Team RAG scope is **team-level** (``agent_id=None``): an agent with its
    own embedding override writes to a different collection and is not retrieved here
    yet (tracked gap, Bug 1 — chosen "team-level now" slice).

    Returns ``None`` (retrieval simply not attached, logged) on any model-resolution
    failure — most commonly no embedding model configured — so a knowledge-store wiring
    problem disables the tools **without** collapsing the whole mesh to the stub path.
    """
    try:
        embedding_model_id = await resolve_embedding_model_id(
            session, org_id=org_id, team_id=team_id, agent_id=None
        )
        conn_repo, cat_repo = await _load_conn_cat_repos(session, org_id=org_id)
        embeddings = EmbeddingsResolver(
            connections=conn_repo, catalog=cat_repo, secrets=build_secret_resolver(settings)
        ).resolve(embedding_model_id)
    except ModelResolutionError as exc:
        # Targeted (not a bare except): only model-resolution failures land here, and
        # they mean "retrieval can't be wired", not "the run is broken". Logged, not silent.
        logger.info(
            "Team %s / conversation: knowledge tools not attached — %s: %s",
            team_id,
            type(exc).__name__,
            exc,
        )
        return None
    return build_knowledge_vectorstore(
        embeddings=embeddings,
        connection=knowledge_connection_url(settings.LANGGRAPH_PG_URL),
        collection_name=knowledge_collection_name(embedding_model_id),
    )


class _SnapshotIncomplete(RuntimeError):
    """A team's config cannot form a real mesh context (→ stub path)."""
