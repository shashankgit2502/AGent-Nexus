"""The ``code_interpreter`` capability tool — run Python, return output (ARCH §10.5.4).

What the **code_interpreter capability** adds: a tool that executes model-generated
Python and returns its ``stdout``/``stderr`` so an agent can compute, parse, or
verify numbers rather than guess them.

Security (R5) — why it is OFF by default
----------------------------------------
Executing model-generated code is a real risk, so this is gated behind
``CODE_INTERPRETER_ENABLED`` (default ``False``); disabled, the tool is still present
and callable but returns an honest "not enabled" message (R3 — no silent fakery).
When enabled, code runs in a **subprocess** (a fresh ``python -c``) with a hard
timeout and a throwaway working directory — basic isolation that prevents an infinite
loop or a crash from taking down the worker. It is **not** a hardened sandbox: it does
not restrict filesystem or network access. For untrusted multi-tenant use, point this
at an external sandbox (E2B / Riza / a container) — the tool boundary stays the same.
"""

from __future__ import annotations

import asyncio
import logging
import subprocess  # noqa: S404 — used to run the agent's code in an isolated child process
import sys
import tempfile
from typing import Any

from langchain_core.tools import BaseTool, tool

logger = logging.getLogger(__name__)

_NOT_ENABLED = (
    "code_interpreter is not enabled on this deployment (set CODE_INTERPRETER_ENABLED). "
    "Reason through the problem and show your working instead of executing code."
)
_MAX_OUTPUT_CHARS = 8_000


def _truncate(text: str) -> str:
    return text if len(text) <= _MAX_OUTPUT_CHARS else text[:_MAX_OUTPUT_CHARS] + "\n…[truncated]"


def _exec_python(code: str, *, timeout: float) -> subprocess.CompletedProcess[str]:
    """Run ``python -I -c <code>`` in a throwaway cwd with a timeout (blocking).

    Uses the blocking ``subprocess.run`` (driven off the event loop via
    ``asyncio.to_thread`` by :func:`run_python`) deliberately: ``asyncio``'s subprocess
    support is **not** available on Windows under the ``SelectorEventLoop`` this app
    requires for psycopg, whereas ``subprocess.run`` works on every platform/loop.
    """
    with tempfile.TemporaryDirectory(prefix="nexagi-code-") as cwd:
        return subprocess.run(  # noqa: S603 — fixed argv (no shell); the agent's code is the -c arg
            [sys.executable, "-I", "-c", code],  # -I: isolated mode (ignore env/user site)
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )


async def run_python(code: str, *, timeout: float) -> str:
    """Execute ``code`` in a subprocess and return its combined output (see module note).

    A timeout terminates the child and reports it, so a runaway snippet can never hang
    the round. Output is captured and length-capped before returning.
    """
    try:
        proc = await asyncio.to_thread(_exec_python, code, timeout=timeout)
    except subprocess.TimeoutExpired:
        return f"code_interpreter: execution timed out after {timeout:g}s."
    except Exception as exc:  # noqa: BLE001 — surfaced to the agent as an observation.
        logger.warning("code_interpreter could not run: %s: %s", type(exc).__name__, exc)
        return f"code_interpreter failed to start ({type(exc).__name__}): {exc}"

    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    parts: list[str] = []
    if out:
        parts.append(f"stdout:\n{out}")
    if err:
        parts.append(f"stderr:\n{err}")
    if not parts:
        parts.append("(no output)")
    if proc.returncode:
        parts.append(f"(exit code {proc.returncode})")
    return _truncate("\n\n".join(parts))


def make_code_interpreter_tool(settings: Any) -> BaseTool:
    """Build the ``code_interpreter`` tool (real subprocess only when enabled)."""
    enabled = bool(settings.CODE_INTERPRETER_ENABLED)
    timeout = float(settings.CODE_INTERPRETER_TIMEOUT_S)

    @tool
    async def code_interpreter(code: str) -> str:
        """Execute Python code in a subprocess and return its stdout/stderr."""
        if not enabled:
            return _NOT_ENABLED
        return await run_python(code, timeout=timeout)

    return code_interpreter
