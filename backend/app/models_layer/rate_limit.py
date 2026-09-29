"""Client-side request pacing to stay under a provider's rate limit (R1/R2).

Why this exists (root cause, R3)
--------------------------------
A collaboration round fans out to every active agent in parallel via ``Send()``
(ARCH §7). All N agents therefore call the *same* provider model in one super-step
— a burst of N large requests inside a single minute. On a constrained key (e.g.
OpenAI tier-1 gpt-4o at 30_000 tokens/min) that burst alone meets or exceeds the
tokens-per-minute limit, so the provider 429s the round; the next round bursts
again and 429s again — the cascade seen in the logs.

The fix is **client-side pacing**: gate outgoing requests so a rolling window never
exceeds the provider's budget, instead of firing everything and reacting to 429s.

Primitive choice (R2 — do not hand-roll)
-----------------------------------------
LangChain ships ``InMemoryRateLimiter`` (``langchain_core.rate_limiters``), accepted
by ``init_chat_model(..., rate_limiter=...)`` and thread-safe for sharing across the
mesh. We use it rather than a custom limiter. We build **one** instance per run and
inject it into every model the resolver creates, so the budget bounds *aggregate*
mesh throughput — not each agent independently (N independent limiters would not cap
the burst at all).

Known limitation (R1 — from the LangChain docs)
-----------------------------------------------
``InMemoryRateLimiter`` limits the number of *requests* per unit time, not their
*token* size. A tokens-per-minute (TPM) limit is therefore approximated by
converting it to a requests-per-minute budget using the run's typical request size
(see :data:`Settings.AGENT_MAX_REQUESTS_PER_MINUTE`). The SDK's own exponential-
backoff 429 retry (LangChain chat models retry up to 6× by default) stays as the
backstop for the occasional request that still races the limit; this pacer's job is
to keep us under the limit so that backstop rarely fires.
"""

from __future__ import annotations

import logging

from langchain_core.rate_limiters import BaseRateLimiter, InMemoryRateLimiter

from app.core.config import Settings

logger = logging.getLogger(__name__)

# The limiter wakes this often to check whether a request slot has freed up. Small
# enough that a freed slot is claimed promptly without busy-waiting (LangChain docs
# default). Not a tunable — it does not affect the enforced rate, only latency to
# notice a free slot.
_CHECK_EVERY_N_SECONDS = 0.1


def build_rate_limiter(settings: Settings) -> BaseRateLimiter | None:
    """Build the run-shared request pacer, or ``None`` when pacing is disabled.

    Returns ``None`` when ``AGENT_MAX_REQUESTS_PER_MINUTE <= 0`` (the default), so an
    unconfigured deployment behaves exactly as before (SDK 429-retry only, no pacing).
    When configured, the returned limiter is shared by every model the resolver builds
    for the run, bounding the whole mesh to the configured requests-per-minute.
    """
    rpm = settings.AGENT_MAX_REQUESTS_PER_MINUTE
    if rpm <= 0:
        return None
    requests_per_second = rpm / 60.0
    # max_bucket_size must be ≥ 1 (a zero/sub-one bucket can never admit a request).
    burst = max(1.0, settings.AGENT_RATE_LIMIT_BURST)
    logger.info(
        "client-side model pacing ON: %.2f req/min (%.4f req/s), burst=%.0f",
        rpm,
        requests_per_second,
        burst,
    )
    return InMemoryRateLimiter(
        requests_per_second=requests_per_second,
        check_every_n_seconds=_CHECK_EVERY_N_SECONDS,
        max_bucket_size=burst,
    )
