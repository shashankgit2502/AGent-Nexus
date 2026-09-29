"""Structured logging configuration.

Local: human-readable lines to stdout.
Production: JSON records to stdout (consumed by the log aggregator).

Design rules (learned from the 2026-07-03 log-noise RCA — a 3,000-line log for a
12-second run made real signals impossible to find):

1. **One handler, on the root logger.** Everything propagates to it; nothing else
   attaches its own handler (that's why the SQLAlchemy ``echo`` flag is banned —
   it installs a second handler and every statement prints twice).
2. **UTF-8 console, always.** Windows consoles default to a legacy codepage
   (cp1252) that cannot encode characters routinely present in LLM payloads
   (``→``, ``•``, non-Latin scripts); the logging module then prints a
   ``--- Logging error ---`` traceback *instead of* the record — fake crashes in
   the log. The stream is reconfigured to UTF-8 with ``errors="replace"`` so one
   character can never eat a log line.
3. **Third-party noise floor is WARNING.** ``LOG_LEVEL`` tunes *our* code
   (``app.*``); it must never re-open the ``openai`` request-payload firehose or
   the SQL echo. SQL logging has its own explicit switch (``LOG_SQL``).
"""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

# Libraries whose INFO/DEBUG output is high-volume diagnostics (full request
# payloads, connection chatter), not application signal. Pinned to WARNING even
# when LOG_LEVEL=DEBUG — debugging the app should not mean drowning in them.
_NOISY_LOGGERS = (
    "httpx",
    "httpcore",
    "urllib3",
    "asyncio",
    "openai",       # DEBUG dumps every full request payload (~8KB prompts × agents)
    "langsmith",    # tracing-disabled notices on every call
    "websockets",
)


class _JsonFormatter(logging.Formatter):
    """Emit log records as single-line JSON for machine consumption in prod."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging(
    app_env: str = "local", *, level: str = "INFO", log_sql: bool = False
) -> None:
    """Set up logging for the application (see module docstring for the rules).

    Call once at startup (inside the FastAPI lifespan). Never use print().

    Args:
        app_env: ``local`` gets human-readable lines; anything else gets JSON.
        level: root level for application loggers (``Settings.LOG_LEVEL``).
            An unknown name falls back to INFO rather than raising at boot.
        log_sql: when True, ``sqlalchemy.engine`` logs statements at INFO through
            the single root handler (``Settings.LOG_SQL``); the engine's ``echo``
            flag must stay off (rule 1).
    """
    root = logging.getLogger()
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    # Rule 2: UTF-8 console. `reconfigure` exists on TextIOWrapper (real stdout);
    # guarded so exotic streams (pytest capture, service wrappers) stay untouched.
    if hasattr(handler.stream, "reconfigure"):
        handler.stream.reconfigure(encoding="utf-8", errors="replace")

    if app_env == "local":
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
                datefmt="%H:%M:%S",
            )
        )
    else:
        handler.setFormatter(_JsonFormatter())

    resolved = logging.getLevelNamesMapping().get(level.upper(), logging.INFO)
    root.setLevel(resolved)
    root.addHandler(handler)

    # Rule 3: third-party noise floor.
    for noisy in _NOISY_LOGGERS:
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # SQL visibility is an explicit opt-in switch, not a side effect of APP_ENV.
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.INFO if log_sql else logging.WARNING
    )
