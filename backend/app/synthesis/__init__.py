"""Final synthesis — merge the consensus result into one output (ARCHITECTURE.md §4.6)."""

from app.synthesis.synthesizer import LLMSynthesizer, render_synthesis_messages

__all__ = ["LLMSynthesizer", "render_synthesis_messages"]
