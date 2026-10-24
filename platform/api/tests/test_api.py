from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from platform_api.github import GitHubError, PullRequestInfo
from platform_api.main import app, build_services
from platform_api.settings import Settings

REPO_ROOT = Path(__file__).resolve().parents[3]


class FakeGitHub:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.files: dict[str, tuple[str, str, str]] = {}  # branch -> (path, content, message)
        self.prs: list[dict] = []

    def create_branch_with_file(self, branch: str, path: str, content: str, message: str) -> str:
        if self.fail:
            raise GitHubError("boom")
        self.files[branch] = (path, content, message)
        return "abc123"

    def open_pull_request(
        self, title: str, body: str, head: str, labels: list[str]
    ) -> PullRequestInfo:
        number = len(self.prs) + 1
        self.prs.append({"title": title, "body": body, "head": head, "labels": labels})
        return PullRequestInfo(
            {"number": number, "html_url": f"https://github.com/x/y/pull/{number}"}
        )


@pytest.fixture
def client(tmp_path: Path):
    def make(github):
        settings = Settings(
            database_url=f"sqlite:///{tmp_path / 'test.db'}",
            repo_root=REPO_ROOT,
            catalog_dir=REPO_ROOT / "platform" / "catalog",
        )
        app.state.services = build_services(settings, github=github)
        return TestClient(app)

    return make


def test_catalog_endpoints(client) -> None:
    c = client(FakeGitHub())
    types = c.get("/catalog").json()
    assert {t["type"] for t in types} == {"s3-bucket", "dynamodb-table", "k8s-namespace"}
    one = c.get("/catalog/s3-bucket").json()
    assert one["module"] == "infra/terraform/modules/s3-bucket"
    assert c.get("/catalog/nope").status_code == 404


def test_request_opens_a_pr_with_one_file(client) -> None:
    gh = FakeGitHub()
    c = client(gh)
    resp = c.post(
        "/requests",
        json={
            "type": "s3-bucket",
            "inputs": {"name": "demo-uploads", "team": "web", "cost_center": "cc-100"},
            "requested_by": "asaf",
        },
    )
    assert resp.status_code == 201, resp.text
    req = resp.json()
    assert req["state"] == "pr-opened"
    assert req["pr_number"] == 1
    assert req["branch"] == f"request/{req['id']}"
    assert req["inputs"]["retention"] == "90d"  # default filled

    path, content, message = gh.files[req["branch"]]
    assert path == f"infra/terraform/envs/local/requests/{req['id']}.tf"
    assert f'module "{req["id"]}"' in content
    assert '"managed-by"  = "platform"' in content
    assert req["id"] in message

    pr = gh.prs[0]
    assert pr["title"] == "[s3-bucket] demo-uploads for team web"
    assert "platform-request" in pr["labels"]
    assert f'"request_id": "{req["id"]}"' in pr["body"]

    events = c.get("/audit", params={"request": req["id"]}).json()
    assert [e["event"] for e in events] == ["requested", "pr-opened"]
    assert events[0]["actor"] == "asaf" and events[0]["actor_type"] == "human"
    assert events[1]["actor"] == "platform-api" and events[1]["actor_type"] == "system"

    assert c.get(f"/requests/{req['id']}").json()["pr_url"].endswith("/pull/1")
    assert len(c.get("/requests", params={"state": "pr-opened"}).json()) == 1


def test_bad_inputs_are_422(client) -> None:
    c = client(FakeGitHub())
    resp = c.post(
        "/requests",
        json={"type": "s3-bucket", "inputs": {"name": "BAD"}, "requested_by": "asaf"},
    )
    assert resp.status_code == 422
    assert "name" in resp.json()["detail"]


def test_type_not_in_environment_is_422(client) -> None:
    c = client(FakeGitHub())
    resp = c.post(
        "/requests",
        json={
            "type": "k8s-namespace",
            "environment": "dev",
            "inputs": {"name": "team-web-dev", "team": "web", "cost_center": "cc-100"},
            "requested_by": "asaf",
        },
    )
    assert resp.status_code == 422


def test_github_failure_is_recorded(client) -> None:
    c = client(FakeGitHub(fail=True))
    resp = c.post(
        "/requests",
        json={
            "type": "s3-bucket",
            "inputs": {"name": "demo-uploads", "team": "web", "cost_center": "cc-100"},
            "requested_by": "asaf",
        },
    )
    assert resp.status_code == 201
    req = resp.json()
    assert req["state"] == "failed"
    assert "boom" in req["error"]
    events = c.get("/audit", params={"request": req["id"]}).json()
    assert [e["event"] for e in events] == ["requested", "failed"]


def test_without_github_configured(client) -> None:
    c = client(None)
    resp = c.post(
        "/requests",
        json={
            "type": "s3-bucket",
            "inputs": {"name": "demo-uploads", "team": "web", "cost_center": "cc-100"},
            "requested_by": "asaf",
        },
    )
    assert resp.json()["state"] == "failed"
    assert "not configured" in resp.json()["error"]
