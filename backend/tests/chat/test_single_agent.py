"""Unit tests for the no-team chat helpers + the conversation create contract."""

from __future__ import annotations

from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import ValidationError

from app.chat.single_agent import _last_ai_text, _ref_from_model_ref
from app.schemas.conversations import ConversationCreate


class TestRefFromModelRef:
    def test_profile_only(self) -> None:
        pid = uuid4()
        ref = _ref_from_model_ref({"profile_id": str(pid)})
        assert ref.profile_id == pid
        assert ref.override_model_id is None

    def test_profile_and_model_override(self) -> None:
        pid, mid = uuid4(), uuid4()
        ref = _ref_from_model_ref({"profile_id": str(pid), "model_id": str(mid)})
        assert ref.override_model_id == mid

    def test_missing_profile_id_raises(self) -> None:
        with pytest.raises(ValueError, match="profile_id"):
            _ref_from_model_ref({"model_id": str(uuid4())})

    def test_none_raises(self) -> None:
        with pytest.raises(ValueError, match="profile_id"):
            _ref_from_model_ref(None)


class TestLastAiText:
    def test_extracts_last_ai_message(self) -> None:
        result = {"messages": [HumanMessage(content="hi"), AIMessage(content="hello there")]}
        assert _last_ai_text(result) == "hello there"

    def test_no_ai_message_raises(self) -> None:
        # A contract violation (distinct from the stub path) must surface, not hide (R3).
        with pytest.raises(RuntimeError, match="no AIMessage"):
            _last_ai_text({"messages": [HumanMessage(content="hi")]})


class TestConversationCreateContract:
    def test_no_team_requires_model_ref(self) -> None:
        with pytest.raises(ValidationError, match="model_ref"):
            ConversationCreate()  # no team, no model_ref

    def test_no_team_with_model_ref_ok(self) -> None:
        cfg = ConversationCreate(model_ref={"profile_id": str(uuid4())})
        assert cfg.team_id is None

    def test_playground_requires_team(self) -> None:
        with pytest.raises(ValidationError, match="playground"):
            ConversationCreate(is_playground=True, model_ref={"profile_id": str(uuid4())})

    def test_team_chat_ok(self) -> None:
        cfg = ConversationCreate(team_id=uuid4())
        assert cfg.model_ref is None
