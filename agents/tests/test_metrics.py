"""/metrics: runs, steps, tokens, tool calls by outcome, computed from the tables."""

from pathlib import Path

from tests.test_server import ALERT, make_client


def test_agent_metrics(tmp_path: Path) -> None:
    client, runner, store = make_client(tmp_path)
    store.create_run("run-1", "incident-triage", "fp-1", ALERT)
    from datetime import UTC, datetime

    store.add_step(
        "run-1",
        {"tool": "kubernetes.kubectl_describe", "ok": True, "at": datetime.now(UTC).isoformat()},
    )
    store.finish_run("run-1", status="done", report="r", usage={"total_tokens": 1200})
    store.create_run("run-2", "incident-triage", "fp-2", ALERT)
    store.finish_run("run-2", status="failed", error="boom")
    store.audit(
        "agent.tool_call",
        actor="incident-triage",
        run_id="run-1",
        target="kubernetes.kubectl_describe",
        outcome="ok",
    )
    store.audit(
        "agent.tool_refused",
        actor="incident-triage",
        run_id="run-1",
        target="kubernetes.kubectl_delete",
        outcome="refused",
    )

    with client:
        text = client.get("/metrics").text
    assert 'agent_runs{status="done"} 1.0' in text and 'agent_runs{status="failed"} 1.0' in text
    assert "agent_run_steps_mean 1.0" in text
    assert "agent_run_tokens_mean 1200.0" in text
    assert 'agent_run_duration_seconds{quantile="0.5"}' in text
    assert 'agent_run_first_tool_seconds{quantile="0.5"}' in text
    assert 'agent_tool_calls{outcome="refused",tool="kubernetes.kubectl_delete"} 1.0' in text
    assert "agent_prompt_info{version=" in text
