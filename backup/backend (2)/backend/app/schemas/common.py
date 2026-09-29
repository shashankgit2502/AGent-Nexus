"""Shared Pydantic v2 base for API boundary DTOs (R5).

``ORMModel`` enables ``from_attributes`` so read models project directly from
SQLAlchemy ORM instances.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    """Read-model base: build from ORM attributes."""

    model_config = ConfigDict(from_attributes=True)
