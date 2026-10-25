"""/metrics: numbers computed from the request and audit tables."""

from pathlib import Path

from fastapi.testclient import TestClient

from platform_api.main import app, build_services
from platform_api.models import RequestState
from platform_api.settings import Settings

REPO_ROOT = Path(__file__).resolve().parents[3]


def make_client(tmp_path: Path) -> TestClient:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'm.db'}",
        repo_root=REPO_ROOT,
        catalog_dir=REPO_ROOT / "platform" / "catalog",
    )
    app.state.services = build_services(settings, github=None)
    return TestClient(app)


def test_metrics_reflect_requests_and_events(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    store = app.state.services.store
    store.create_request("r-1", "s3-bucket", "local", {"name": "a"}, "asaf")
    store.transition("r-1", RequestState.PR_OPENED, actor="platform-api")
    store.transition("r-1", RequestState.APPROVED, actor="asaf", actor_type="human")
    store.transition("r-1", RequestState.DEPLOYED, actor="apply-worker")
    store.create_request("r-2", "s3-bucket", "local", {"name": "b"}, "asaf")

    with client:
        text = client.get("/metrics").text
    assert 'platform_requests{state="deployed"} 1.0' in text
    assert 'platform_requests{state="requested"} 1.0' in text
    assert "platform_requests_created_7d 2.0" in text
    assert 'platform_request_time_to_deployed_seconds{quantile="0.5"}' in text
    assert "platform_request_time_to_deployed_seconds_samples 1.0" in text
    assert 'platform_approval_wait_seconds{quantile="0.95"}' in text
    assert 'platform_audit_events{event="approved",outcome="ok"} 1.0' in text


def test_metrics_on_an_empty_database(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    with client:
        text = client.get("/metrics").text
    assert "platform_requests_created_7d 0.0" in text
    assert "platform_request_time_to_deployed_seconds_samples 0.0" in text
