"""Dry run: the real agent (prompt, runbooks, model settings) against a fixture.

No cluster, no GitHub, no MCP servers: the fixture's canned outputs stand in
for the tools, and every model turn is printed as it happens. Use it to see
what the model actually does before a live run. Minutes on a CPU model.

    cd agents && OLLAMA_BASE_URL=http://host.docker.internal:11434 \\
        .venv/bin/python dryrun.py [evals/fixtures/<scenario>.yaml]
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
os.environ.setdefault("AGENTS_DIR", str(HERE))

from pydantic_ai import Agent  # noqa: E402
from pydantic_ai.messages import (  # noqa: E402
    RetryPromptPart,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.usage import UsageLimits  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402

from runtime.audit import Store  # noqa: E402
from runtime.evalrun import verdict  # noqa: E402
from runtime.runner import IncidentReport, build_runner, new_run_id  # noqa: E402
from runtime.tools.fixture import Fixture  # noqa: E402
from runtime.tools.local import make_local_toolset  # noqa: E402
from runtime.tools.registry import ToolGuard, build_toolsets  # noqa: E402

T0 = time.monotonic()


def t() -> str:
    return f"[{time.monotonic() - T0:6.0f}s]"


def show_response(resp: Any) -> None:
    for part in resp.parts:
        if isinstance(part, ThinkingPart):
            print(f"{t()} model THINKING {len(part.content)} chars")
        elif isinstance(part, TextPart):
            print(f"{t()} model TEXT ({len(part.content)} chars): {part.content[:300]!r}")
        elif isinstance(part, ToolCallPart):
            args = part.args if isinstance(part.args, str) else json.dumps(part.args)
            print(f"{t()} model TOOL {part.tool_name}({args[:220]})")
    u = resp.usage
    print(f"{t()}   usage: in={u.input_tokens} out={u.output_tokens}")


def show_request(req: Any) -> None:
    for part in req.parts:
        if isinstance(part, ToolReturnPart):
            c = part.content if isinstance(part.content, str) else json.dumps(part.content)
            print(f"{t()} tool RETURN {part.tool_name}: {c[:160]!r}...")
        elif isinstance(part, RetryPromptPart):
            c = part.content if isinstance(part.content, str) else json.dumps(part.content)
            print(f"{t()} RETRY prompt: {c[:200]!r}")


async def main(fixture_path: Path) -> int:
    fixture = Fixture.load(fixture_path)
    db = Path(tempfile.gettempdir()) / "agent-dryrun.db"
    store = Store(create_engine(f"sqlite:///{db}"))
    runner = build_runner(store)
    m = runner.spec.manifest
    if fixture.overrides:
        m = m.model_copy(update=dict(fixture.overrides))
    run_id = new_run_id()
    alert = fixture.alert
    fingerprint = str(alert.get("fingerprint") or run_id)
    store.create_run(run_id, m.name, fingerprint, alert)
    guard = ToolGuard(set(m.allowed_tools), set(m.allowed_namespaces), m.name, run_id, store)
    toolsets = build_toolsets(
        runner.mcp_doc, m, guard, make_local_toolset(runner.repo), fixture=fixture
    )
    cfg = runner.model_cfg
    print(f"fixture: {fixture.name} ({fixture.description})")
    print(f"model: {cfg.provider}:{cfg.name} at {cfg.ollama_base_url}")
    instructions = runner.instructions(alert)
    print(
        f"instructions: {len(instructions)} chars, max_steps={m.max_steps}, budget={m.token_budget}"
    )
    agent: Agent[None, IncidentReport] = Agent(
        runner.model,
        name=m.name,
        instructions=instructions,
        toolsets=toolsets,
        output_type=IncidentReport,
        retries=2,
    )
    limits = UsageLimits(request_limit=m.max_steps, total_tokens_limit=m.token_budget)
    status, error, report = "done", None, ""
    try:
        async with agent.iter(runner.user_prompt(alert, fingerprint), usage_limits=limits) as run:
            async for node in run:
                if Agent.is_call_tools_node(node):
                    show_response(node.model_response)
                elif Agent.is_model_request_node(node):
                    show_request(node.request)
        result = run.result
        assert result is not None
        out = result.output
        report = out.markdown() if isinstance(out, IncidentReport) else str(out)
        usage = result.usage() if callable(result.usage) else result.usage
        print(f"{t()} usage total: {usage}")
    except Exception as e:  # noqa: BLE001
        status, error = "failed", f"{type(e).__name__}: {str(e)[:400]}"
        print(f"{t()} FAILED: {error}")
    print("=== REPORT ===")
    print(report)
    record = {
        "status": status,
        "error": error,
        "steps": len(guard.records),
        "tools": [r.tool for r in guard.records],
        "report": report,
        "proposals": fixture.proposals,
        "expect": fixture.expect.model_dump(),
    }
    failures = verdict(record)
    print("=== VERDICT ===")
    print("PASS" if not failures else "FAIL")
    for f in failures:
        print(f"  - {f}")
    return 1 if failures else 0


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "evals/fixtures/imagepullbackoff.yaml"
    sys.exit(asyncio.run(main((HERE / arg) if not Path(arg).is_absolute() else Path(arg))))
