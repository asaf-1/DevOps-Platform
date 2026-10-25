"""Runner.run end to end with Pydantic AI's TestModel: no MCP servers, no network.

TestModel calls every available tool once with made-up arguments, then
returns the typed report. That exercises the guard, the local toolset, the
report rendering and the usage bookkeeping, which a live run only reaches
after fifteen minutes on this laptop.
"""

import asyncio
from pathlib import Path

from pydantic_ai.models.test import TestModel
from sqlalchemy import create_engine

from runtime.audit import Store
from runtime.knowledge import Knowledge
from runtime.manifest import CapabilityMap
from runtime.providers import ModelConfig
from runtime.runner import Runner, load_agent

AGENTS = Path(__file__).resolve().parents[1]
ALERT = {
    "fingerprint": "fp-runner",
    "labels": {
        "alertname": "DemoAppImagePullBackOff",
        "namespace": "demo",
        "pod": "demo-app-1",
        "container": "demo-app",
        "severity": "critical",
    },
    "annotations": {"summary": "demo-app-1 cannot pull its image"},
}


def test_run_finishes_with_report_and_usage(tmp_path: Path) -> None:
    store = Store(create_engine(f"sqlite:///{tmp_path / 'r.db'}"))
    capmap = CapabilityMap.load(
        AGENTS / "tools" / "capabilities.yaml", AGENTS / "tools" / "mcp.yaml"
    )
    spec = load_agent(AGENTS / "incident_triage", capmap)
    runner = Runner(
        store,
        spec,
        {"servers": {}},  # no MCP servers: only the local toolset is built
        Knowledge.load(AGENTS.parent / "docs" / "runbooks"),
        model=TestModel(),
        model_cfg=ModelConfig(provider="ollama", name="test"),
    )
    store.create_run("run-t", spec.manifest.name, "fp-runner", ALERT)
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider

    if not isinstance(trace.get_tracer_provider(), TracerProvider):
        trace.set_tracer_provider(TracerProvider())
    run = asyncio.run(runner.run("run-t", ALERT))
    assert run["status"] == "done", run.get("error")
    assert run["trace_id"] and len(run["trace_id"]) == 32  # one trace per run
    assert "## Symptoms" in run["report"] and "## Proposed change" in run["report"]
    assert run["usage"]["requests"] >= 1 and run["usage"]["tool_calls"] >= 1
    # TestModel's made-up path is refused by replace_line, never sent to GitHub
    assert all(s["tool"] == "local.replace_line" for s in run["steps"])
    prompt = runner.user_prompt(ALERT, "fp-runner")
    assert "gitops/apps/demo-app/deployment.yaml" in prompt
