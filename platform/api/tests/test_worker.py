from pathlib import Path
from typing import Any

import pytest

from platform_api.github import GitHubError
from platform_api.models import RequestState
from platform_api.storage import Store, make_engine
from platform_api.worker import TerraformResult, Worker, merge_outputs_into_configmap

CONFIGMAP = """apiVersion: v1
kind: ConfigMap
metadata:
  name: demo-app-config
  namespace: demo
data:
  GREETING: hello
"""


class FakeGitHub:
    """A PR whose state the test moves along: open -> checks passed -> merged -> approved."""

    def __init__(self) -> None:
        self.pr: dict[str, Any] = {
            "number": 7,
            "state": "open",
            "merged_at": None,
            "merge_commit_sha": None,
            "merged_by": None,
            "head": {"sha": "head111"},
        }
        self.runs: dict[tuple[str, str], str | None] = {}
        self.files: dict[str, tuple[str, str]] = {
            "gitops/apps/demo-app/configmap.yaml": (CONFIGMAP, "sha0")
        }
        self.commits: list[tuple[str, str, str]] = []
        self.fail_put = False

    def get_pull_request(self, number: int) -> dict[str, Any]:
        assert number == 7
        return dict(self.pr)

    def workflow_run_conclusion(self, workflow_file: str, head_sha: str) -> str | None:
        return self.runs.get((workflow_file, head_sha))

    def get_file(self, path: str, ref: str) -> tuple[str, str]:
        if path not in self.files:
            raise GitHubError("404")
        return self.files[path]

    def put_file(self, path: str, content: str, message: str, branch: str, sha: str | None) -> str:
        if self.fail_put:
            raise GitHubError("put failed")
        self.files[path] = (content, "sha1")
        self.commits.append((path, message, branch))
        return "commit123"


@pytest.fixture
def world(tmp_path: Path):
    store = Store(make_engine(f"sqlite:///{tmp_path / 'w.db'}"))
    gh = FakeGitHub()
    fetched: list[str] = []
    applies: list[tuple[str, str]] = []
    result = {
        "value": TerraformResult(
            ok=True,
            outputs={
                "bucket_name": "demo-uploads",
                "bucket_arn": "arn:aws:s3:::demo-uploads",
                "bucket_id": "demo-uploads",
            },
        )
    }

    def fetch_repo(sha: str) -> Path:
        fetched.append(sha)
        return tmp_path / "repo"

    def run_apply(repo_dir: Path, environment: str, request_id: str) -> TerraformResult:
        applies.append((environment, request_id))
        return result["value"]

    worker = Worker(store, gh, fetch_repo, run_apply, base_branch="main")
    req = store.create_request(
        "r-abc123",
        "s3-bucket",
        "local",
        {"name": "demo-uploads", "team": "web", "cost_center": "cc-100"},
        "asaf",
    )
    store.transition(
        req.id,
        RequestState.PR_OPENED,
        actor="platform-api",
        branch="request/r-abc123",
        pr_number=7,
        pr_url="https://x/pull/7",
    )
    return store, gh, worker, fetched, applies, result


def events(store: Store, rid: str) -> list[str]:
    return [e.event for e in store.list_events(rid)]


def test_full_happy_path(world) -> None:
    store, gh, worker, fetched, applies, _ = world

    # nothing has run yet on the PR
    assert worker.run_once() == []
    assert store.get_request("r-abc123").state == RequestState.PR_OPENED

    # iac-pr succeeded on the head commit -> planned, with plan-ok and policy-ok events
    gh.runs[("iac-pr.yml", "head111")] = "success"
    assert worker.run_once() == ["r-abc123"]
    assert store.get_request("r-abc123").state == RequestState.PLANNED
    assert events(store, "r-abc123") == [
        "requested",
        "pr-opened",
        "plan-ok",
        "policy-ok",
        "planned",
    ]

    # merged, approval run pending -> still planned
    gh.pr.update(
        {
            "state": "closed",
            "merged_at": "2026-10-24T21:00:00Z",
            "merge_commit_sha": "merge222",
            "merged_by": {"login": "asaf"},
        }
    )
    worker.run_once()
    assert store.get_request("r-abc123").state == RequestState.PLANNED

    # approval run succeeded -> approved -> applied -> deployed, each in its own pass
    gh.runs[("iac-approve.yml", "merge222")] = "success"
    worker.run_once()
    req = store.get_request("r-abc123")
    assert req.state == RequestState.DEPLOYED
    assert req.outputs["bucket_name"] == "demo-uploads"
    assert fetched == ["merge222"]
    assert applies == [("local", "r-abc123")]

    names = events(store, "r-abc123")
    assert names[-3:] == ["approved", "applied", "deployed"]
    approved = [e for e in store.list_events("r-abc123") if e.event == "approved"][0]
    assert approved.actor_type == "human" and approved.details["merged_by"] == "asaf"

    # outputs landed in the demo app ConfigMap, committed to main
    content, _ = gh.files["gitops/apps/demo-app/configmap.yaml"]
    assert "BUCKET_NAME: demo-uploads" in content
    assert "r-abc123.bucket_arn: arn:aws:s3:::demo-uploads" in content
    assert "GREETING: hello" in content
    assert gh.commits[0][2] == "main" and "r-abc123" in gh.commits[0][1]

    # idempotent: another pass changes nothing
    assert worker.run_once() == []


def test_closed_without_merge_fails(world) -> None:
    store, gh, worker, *_ = world
    gh.pr.update({"state": "closed", "merged_at": None})
    worker.run_once()
    req = store.get_request("r-abc123")
    assert req.state == RequestState.FAILED
    assert "without merging" in req.error


def test_apply_failure_is_recorded(world) -> None:
    store, gh, worker, _, _, result = world
    gh.runs[("iac-pr.yml", "head111")] = "success"
    gh.pr.update({"state": "closed", "merged_at": "x", "merge_commit_sha": "merge222"})
    gh.runs[("iac-approve.yml", "merge222")] = "success"
    result["value"] = TerraformResult(ok=False, log="Error: bucket already exists")
    worker.run_once()
    req = store.get_request("r-abc123")
    assert req.state == RequestState.FAILED
    assert req.error == "terraform apply failed"
    failed = [e for e in store.list_events("r-abc123") if e.event == "failed"][0]
    assert "already exists" in failed.details["log_tail"]


def test_configmap_merge_is_stable() -> None:
    from datetime import UTC, datetime

    from platform_api.models import ResourceRequest

    now = datetime.now(UTC)
    req = ResourceRequest(
        id="r-1",
        type="dynamodb-table",
        environment="local",
        inputs={},
        requested_by="a",
        state=RequestState.APPLIED,
        created_at=now,
        updated_at=now,
    )
    once = merge_outputs_into_configmap(CONFIGMAP, req, {"table_name": "orders"})
    twice = merge_outputs_into_configmap(once, req, {"table_name": "orders"})
    assert once == twice
    assert "r-1.table_name: orders" in once
    assert "BUCKET_NAME" not in once
