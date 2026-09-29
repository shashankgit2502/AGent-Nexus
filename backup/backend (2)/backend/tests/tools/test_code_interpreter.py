"""code_interpreter capability tool tests (Bug 5 Part A, ARCH §10.5.4).

Disabled by default → an honest "not enabled" tool. Enabled → a subprocess executes
the code and returns its output; a runaway snippet is killed at the timeout.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.tools.code_interpreter import make_code_interpreter_tool, run_python


@dataclass
class _Settings:
    CODE_INTERPRETER_ENABLED: bool = False
    CODE_INTERPRETER_TIMEOUT_S: float = 10.0


async def test_tool_disabled_is_present_but_honest() -> None:
    tool = make_code_interpreter_tool(_Settings(CODE_INTERPRETER_ENABLED=False))
    assert tool.name == "code_interpreter"
    out = await tool.ainvoke({"code": "print(1)"})
    assert "not enabled" in out


async def test_tool_enabled_executes_and_returns_stdout() -> None:
    tool = make_code_interpreter_tool(_Settings(CODE_INTERPRETER_ENABLED=True))
    out = await tool.ainvoke({"code": "print(6 * 7)"})
    assert "42" in out
    assert "stdout" in out


async def test_run_python_captures_stderr_and_exit_code() -> None:
    out = await run_python("import sys; sys.stderr.write('boom'); sys.exit(3)", timeout=10.0)
    assert "boom" in out
    assert "exit code 3" in out


async def test_run_python_times_out_a_runaway() -> None:
    out = await run_python("while True: pass", timeout=0.5)
    assert "timed out" in out
