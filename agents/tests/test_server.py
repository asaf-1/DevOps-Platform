import time
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from runtime.audit import Store
from runtime.server import Services, app


class FakeRunner:
    """Finishes a run immediately with a canned report."""

    def __init__(self, store: Store) -> None:
        self.store = store
        self.calls: list[tuple[str, dict[str, Any]]] = []

        class Spec:
            class manifest:
                name = "incident-triage"
                mutation = "propose_only"
                allowed_namespaces = ["demo"]
                max_steps = 12
                token_budget = 24000
                namespace_window_minutes = 30
                failed_backoff_minutes = 10

            resolved = {"kubernetes.kubectl_get": {"capability": "read", "target": "cluster"}}

        class Cfg:
            provider = "ollama"
            name = "qwen3:4b-instruct"

        self.spec = Spec()
        self.model_cfg = Cfg()

    async def run(self, run_id: str, alert: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((run_id, alert))
        return self.store.finish_run(
            run_id, status="done", report="## Symptoms\n...", pr_url="https://github.com/x/y/pull/9"
        )


def make_client(tmp_path: Path) -> tuple[TestClient, FakeRunner, Store]:
    store = Store(
        create_engine(f"sqlite:///{tmp_path / 's.db'}", connect_args={"check_same_thread": False})
    )
    runner = FakeRunner(store)
    app.state.services = Services(store, runner)  # type: ignore[arg-type]
    return TestClient(app), runner, store


ALERT = {
    "status": "firing",
    "labels": {
        "alertname": "DemoAppImagePullBackOff",
        "namespace": "demo",
        "pod": "demo-app-1",
        "severity": "critical",
    },
    "annotations": {"summary": "demo-app-1 cannot pull its image"},
    "fingerprint": "fp-123",
}


def _drain(client: TestClient) -> None:
    """Wait for background run tasks started inside the TestClient's event loop."""
    svc = client.app.state.services
    for _ in range(40):
        if not svc.tasks:
            return
        time.sleep(0.05)


def test_webhook_starts_dedupes_and_closes(tmp_path: Path) -> None:
    client, runner, store = make_client(tmp_path)
    with client:
        r = client.post("/webhooks/alertmanager", json={"status": "firing", "alerts": [ALERT]})
        assert r.status_code == 200
        started = r.json()["started"]
        assert len(started) == 1
        _drain(client)
        run = store.get_run(started[0])
        assert run["status"] == "done" and run["pr_url"].endswith("/pull/9")
        assert runner.calls[0][1]["labels"]["alertname"] == "DemoAppImagePullBackOff"

        # same fingerprint again within the dedupe window: skipped
        r2 = client.post("/webhooks/alertmanager", json={"status": "firing", "alerts": [ALERT]})
        assert r2.json() == {"started": [], "skipped": ["fp-123"], "closed": []}

        # resolved: the run gets a closure note
        r3 = client.post(
            "/webhooks/alertmanager",
            json={
                "status": "resolved",
                "alerts": [{**ALERT, "status": "resolved", "endsAt": "2026-10-24T22:00:00Z"}],
            },
        )
        assert r3.json()["closed"] == [started[0]]
        assert "resolved" in store.get_run(started[0])["closure"]

        runs = client.get("/runs").json()
        assert runs[0]["id"] == started[0] and "steps" not in runs[0]
        assert client.get(f"/runs/{started[0]}").json()["report"].startswith("## Symptoms")
        assert client.get("/runs/nope").status_code == 404
        info = client.get("/agent").json()
        assert info["mutation"] == "propose_only" and info["allowed_namespaces"] == ["demo"]


def test_manual_run(tmp_path: Path) -> None:
    client, runner, store = make_client(tmp_path)
    with client:
        r = client.post("/runs", json={"labels": {"alertname": "X", "namespace": "demo"}})
        assert r.status_code == 202
        _drain(client)
        assert store.get_run(r.json()["id"])["status"] == "done"


def test_one_run_per_namespace_at_a_time(tmp_path: Path) -> None:
    """Two alerts for the same broken pod in one payload start one run, not two."""
    client, runner, store = make_client(tmp_path)
    second = {
        **ALERT,
        "labels": {**ALERT["labels"], "alertname": "DemoAppUnavailable"},
        "fingerprint": "fp-456",
    }
    with client:
        r = client.post(
            "/webhooks/alertmanager", json={"status": "firing", "alerts": [ALERT, second]}
        )
        assert r.status_code == 200
        assert len(r.json()["started"]) == 1
        assert r.json()["skipped"] == ["fp-456"]
        _drain(client)
    assert len(runner.calls) == 1


def test_failed_runs_back_off_unless_interrupted(tmp_path: Path) -> None:
    from datetime import timedelta

    from runtime.audit import RunRow, utcnow

    client, runner, store = make_client(tmp_path)
    payload = {"status": "firing", "alerts": [ALERT]}

    def finished_failed(run_id: str, minutes_ago: int, error: str = "boom") -> None:
        store.create_run(run_id, "incident-triage", "fp-123", ALERT)
        store.finish_run(run_id, status="failed", error=error)
        with store.session() as s:
            row = s.get(RunRow, run_id)
            assert row is not None
            row.finished_at = utcnow() - timedelta(minutes=minutes_ago)

    with client:
        finished_failed("run-f1", 2)  # failed 2 minutes ago: back off
        assert client.post("/webhooks/alertmanager", json=payload).json()["skipped"] == ["fp-123"]
        with store.session() as s:  # the same failure, now 11 minutes old: retry
            row = s.get(RunRow, "run-f1")
            assert row is not None
            row.finished_at = utcnow() - timedelta(minutes=11)
        assert len(client.post("/webhooks/alertmanager", json=payload).json()["started"]) == 1
        _drain(client)
        # the retry finished as done just now; drop it to isolate the restart rule
        with store.session() as s:
            for row in s.query(RunRow).filter(RunRow.status == "done"):
                s.delete(row)
        finished_failed("run-f3", 0, error="interrupted by a runtime restart")
        assert len(client.post("/webhooks/alertmanager", json=payload).json()["started"]) == 1
        _drain(client)
