"""Unit tests for ContributionOut (ARCH §22.3 structured output)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agents.contribution import ContributionOut, CritiqueOut


def test_confidence_within_bounds_is_accepted() -> None:
    out = ContributionOut(content="answer", confidence=0.5)
    assert out.confidence == 0.5
    assert out.critiques == []


@pytest.mark.parametrize("bad", [-0.01, 1.01, 2.0])
def test_confidence_outside_unit_interval_is_rejected(bad: float) -> None:
    # The confidence-weighted vote (§8) relies on a 0–1 score; boundary validation
    # at the model edge (R5) prevents a bad self-score poisoning the ranking.
    with pytest.raises(ValidationError):
        ContributionOut(content="answer", confidence=bad)


def test_critiques_carry_target_and_severity() -> None:
    out = ContributionOut(
        content="answer",
        confidence=0.8,
        critiques=[CritiqueOut(target_agent="peer-1", severity="major", content="weak assumption")],
    )
    assert out.critiques[0].target_agent == "peer-1"
    assert out.critiques[0].severity == "major"
