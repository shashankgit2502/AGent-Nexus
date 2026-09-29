"""Layer 3 — Inference Profiles (ARCHITECTURE.md §9 / §27.4, TECHNICAL §11.3).

A *profile* is a reusable bundle of a **default model** plus normalized inference
params (ARCH locked Q1: the profile carries the default model; an agent may
override the model while keeping the profile's params). The profile's params are
exposed as a :class:`~app.models_layer.translate_params.NormalizedParams` so the
resolver can translate them per provider.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models_layer.errors import EntityNotFound
from app.models_layer.translate_params import NormalizedParams, ReasoningLevel, Verbosity


class InferenceProfile(BaseModel):
    """One inference profile (one row of ``inference_profiles``)."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    name: str
    default_model_id: UUID | None = None  # ARCH Q1: profile default model
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    reasoning_level: ReasoningLevel | None = None
    # GPT-5 output-length control. Forwarded only to a reasoning model — a
    # GPT-4-family model rejects the parameter (§ model_capabilities).
    verbosity: Verbosity | None = None
    num_ctx: int | None = None  # Ollama context window override (§9.2)
    json_mode: bool = False

    def normalized_params(self) -> NormalizedParams:
        """Project the profile's params into the provider-agnostic shape."""
        return NormalizedParams(
            temperature=self.temperature,
            top_p=self.top_p,
            max_tokens=self.max_tokens,
            reasoning_level=self.reasoning_level,
            verbosity=self.verbosity,
            num_ctx=self.num_ctx,
            json_mode=self.json_mode,
        )


class ProfileRepository(Protocol):
    """Read access to inference profiles, by id (repository pattern)."""

    def get(self, profile_id: UUID) -> InferenceProfile: ...


class InMemoryProfileRepository:
    """Dict-backed repository for tests and local dev (DB impl in Step 9)."""

    def __init__(self, profiles: list[InferenceProfile] | None = None) -> None:
        self._by_id: dict[UUID, InferenceProfile] = {p.id: p for p in (profiles or [])}

    def add(self, profile: InferenceProfile) -> None:
        self._by_id[profile.id] = profile

    def get(self, profile_id: UUID) -> InferenceProfile:
        try:
            return self._by_id[profile_id]
        except KeyError as exc:
            raise EntityNotFound("inference profile", profile_id) from exc
