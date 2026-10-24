from pathlib import Path

from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel
from pydantic_ai.toolsets import FunctionToolset
from sqlalchemy import create_engine

from runtime.audit import Store
from runtime.tools.registry import ToolGuard, wrap


def make_guard(tmp_path: Path, allowed_tools: set[str]) -> ToolGuard:
    store = Store(create_engine(f"sqlite:///{tmp_path / 'g.db'}"))
    return ToolGuard(
        allowed_tools=allowed_tools,
        allowed_namespaces={"demo"},
        agent="t",
        run_id="run-1",
        store=store,
    )


def test_namespace_rules(tmp_path: Path) -> None:
    g = make_guard(tmp_path, {"kubernetes.kubectl_get"})
    assert g.check("kubernetes.kubectl_get", {"namespace": "demo"}) is None
    assert "outside" in g.check("kubernetes.kubectl_get", {"namespace": "kube-system"})
    assert "required" in g.check("kubernetes.kubectl_get", {"resourceType": "pods"})
    assert "outside" in g.check("kubernetes.kubectl_get", {"command": "get pods -n argocd"})
    assert "all-namespaces" in g.check("kubernetes.kubectl_get", {"command": "get pods -A"})
    assert "allowlist" in g.check("kubernetes.kubectl_delete", {"namespace": "demo"})


def test_github_rules(tmp_path: Path) -> None:
    g = make_guard(
        tmp_path,
        {"github.create_branch", "github.create_or_update_file", "github.create_pull_request"},
    )
    assert g.check("github.create_branch", {"branch": "agent/incident-abc"}) is None
    assert "agent/*" in g.check("github.create_branch", {"branch": "feature/x"})
    assert "never allowed" in g.check(
        "github.create_or_update_file", {"branch": "main"}
    ) or "agent/*" in g.check("github.create_or_update_file", {"branch": "main"})
    assert (
        g.check("github.create_pull_request", {"head": "agent/incident-abc", "base": "main"})
        is None
    )
    assert "target main" in g.check(
        "github.create_pull_request", {"head": "agent/incident-abc", "base": "release"}
    )


async def test_guarded_toolset_records_and_refuses(tmp_path: Path) -> None:
    calls: list[dict] = []

    def kubectl_get(resourceType: str, namespace: str = "") -> str:  # noqa: N803
        """Get resources."""
        calls.append({"resourceType": resourceType, "namespace": namespace})
        return f"pods in {namespace}"

    guard = make_guard(tmp_path, {"kubernetes.kubectl_get"})
    toolset = wrap(FunctionToolset([kubectl_get], id="k"), "kubernetes", guard)

    # TestModel calls the tool with schema-generated args: no real namespace -> refused as text
    model = TestModel(call_tools=["kubernetes_kubectl_get"])
    agent = Agent(model, toolsets=[toolset])
    result = await agent.run("go")
    assert guard.records, "the guard saw the call"
    rec = guard.records[0]
    assert rec.tool == "kubernetes.kubectl_get"
    assert rec.refused is not None and "namespace" in rec.refused
    assert "REFUSED" in str(result.output) or result.output

    # the audit trail has the refusal, written by the agent actor
    from sqlalchemy import select

    from runtime.audit import AuditRow

    with guard.store.session() as s:
        rows = list(s.scalars(select(AuditRow)))
    assert rows and rows[-1].event == "agent.tool_refused" and rows[-1].actor_type == "agent"
    steps = guard.store.get_run("run-1")
    assert steps is None  # no run row created in this unit test; add_step is a no-op then
