"""Chat & conversational layer (ARCH §8.5).

The conversational surface *above* the collaboration engine. It reuses the existing
execution spine — the collab graph for team chat, one ``create_agent`` for no-team
chat — and is **not** a new engine (CLAUDE §3 locked decision).
"""
