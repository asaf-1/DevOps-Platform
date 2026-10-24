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

            resolved = {"kubernetes.kubectl_get": {"capability": "read", "target": "cluster"}}

        class Cfg:
            provider = "ollama"
            name = "qwen3:4b"

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
