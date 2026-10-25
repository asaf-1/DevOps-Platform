"""Fixtures: schema of every recorded scenario, fixture tools, and the eval path."""

import asyncio
import os
from pathlib import Path

from pydantic_ai.models.test import TestModel
from sqlalchemy import create_engine

from runtime.audit import Store
from runtime.evalrun import verdict
from runtime.knowledge import Knowledge
from runtime.manifest import CapabilityMap, load_manifest
from runtime.providers import ModelConfig
from runtime.runner import Runner, load_agent
from runtime.tools.fixture import Fixture, build_fixture_toolsets
from runtime.tools.registry import ToolGuard, build_toolsets

AGENTS = Path(__file__).resolve().parents[1]
FIXTURES = sorted((AGENTS / "evals" / "fixtures").glob("*.yaml"))


def test_every_fixture_loads_and_names_its_scenario() -> None:
    assert len(FIXTURES) >= 10, "the plan asks for at least ten scenarios"
    names = set()
    for path in FIXTURES:
        f = Fixture.load(path)
        assert f.name == path.stem, f"{path.name}: name must match the file name"
        assert f.alert.get("labels", {}).get("namespace") == "demo"
        assert f.description
        names.add(f.name)
    assert len(names) == len(FIXTURES)


def test_fixture_tools_serve_reads_and_record_proposals() -> None:
    f = Fixture.load(AGENTS / "evals" / "fixtures" / "imagepullbackoff.yaml")
    ts = build_fixture_toolsets(f, {"kubernetes", "github", "local"})
    tool = lambda server, name: ts[server].tools[name].function  # noqa: E731

    describe = tool("kubernetes", "kubectl_describe")("pod", "demo-app-1", "demo")
    assert "ImagePullBackOff" in describe
    assert "nothing recorded" in tool("kubernetes", "kubectl_describe")("node", "x", "demo")

    path = "gitops/apps/demo-app/deployment.yaml"
    before = tool("github", "get_file_contents")("asaf-1", "DevOps-Platform", path)
    assert "does-not-exist" in before
    assert "404" in tool("github", "get_file_contents")("asaf-1", "DevOps-Platform", "apps/x.yaml")

    out = tool("local", "replace_line")(
        path, "demo-app:does-not-exist", "demo-app:main", "agent/incident-1", "[agent] fix"
    )
    assert out.startswith("changed line")
    assert "demo-app:main" in tool("github", "get_file_contents")("asaf-1", "DevOps-Platform", path)
    assert "refused" in tool("local", "replace_line")(
        "apps/x.yaml", "a", "b", "agent/incident-1", "m"
    )
    assert "refused" in tool("local", "replace_line")(path, "a", "b", "main", "m")

    pr = tool("github", "create_pull_request")(
        "asaf-1", "DevOps-Platform", "[agent] fix", "agent/incident-1", "main", "body"
    )
    assert "pull/100" in pr
    assert (
        f.proposals["changes"][0]["path"] == path
        and f.proposals["prs"][0]["head"] == "agent/incident-1"
    )


def test_eval_mode_builds_fixture_tools_instead_of_mcp(tmp_path: Path, monkeypatch) -> None:
    manifest = load_manifest(AGENTS / "incident_triage" / "manifest.yaml")
    store = Store(create_engine(f"sqlite:///{tmp_path / 'e.db'}"))
    guard = ToolGuard(set(manifest.allowed_tools), {"demo"}, "t", "run-e", store)
    monkeypatch.setenv("EVAL_MODE", "1")
    monkeypatch.setenv("EVAL_FIXTURE", str(AGENTS / "evals" / "fixtures" / "imagepullbackoff.yaml"))
    mcp_doc = {
        "servers": {"kubernetes": {"command": "does-not-exist"}, "github": {"command": "nope"}}
    }
    toolsets = build_toolsets(mcp_doc, manifest, guard)

    # prefixed(guarded(filtered(fixture toolset))): the innermost ids name the fixture, not MCP
    def innermost(t: object) -> object:
        while getattr(t, "wrapped", None) is not None:
            t = t.wrapped  # type: ignore[attr-defined]
        return t

    inner = {getattr(innermost(t), "id", None) for t in toolsets}
    assert inner == {"fixture-kubernetes", "fixture-github", "fixture-local"}


def test_runner_with_fixture_and_verdict(tmp_path: Path) -> None:
    os.environ.pop("EVAL_MODE", None)
    capmap = CapabilityMap.load(
        AGENTS / "tools" / "capabilities.yaml", AGENTS / "tools" / "mcp.yaml"
    )
    spec = load_agent(AGENTS / "incident_triage", capmap)
    store = Store(create_engine(f"sqlite:///{tmp_path / 'r.db'}"))
    runner = Runner(
        store,
        spec,
        {"servers": {}},
        Knowledge.load(AGENTS.parent / "docs" / "runbooks"),
        model=TestModel(),
        model_cfg=ModelConfig(provider="ollama", name="test"),
    )
    f = Fixture.load(AGENTS / "evals" / "fixtures" / "imagepullbackoff.yaml")
    store.create_run("run-x", spec.manifest.name, "fp-x", f.alert)
    run = asyncio.run(runner.run("run-x", f.alert, fixture=f))
    assert run["status"] == "done"
    assert run["steps"], "TestModel called the fixture tools"
    record = {
        "status": run["status"],
        "steps": len(run["steps"]),
        "tools": [s["tool"] for s in run["steps"]],
        "report": run["report"],
        "proposals": f.proposals,
        "expect": f.expect.model_dump(),
    }
    # TestModel's made-up answer cannot satisfy the real expectations, and verdict says why
    failures = verdict(record)
    assert any("keyword" in x for x in failures)
    # an expectation the record does satisfy
    record["expect"] = {
        "status": "done",
        "max_steps": 20,
        "forbidden_tools": ["kubernetes.kubectl_delete"],
    }
    assert verdict(record) == []
