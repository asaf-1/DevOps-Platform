import json

import httpx
import pytest
from typer.testing import CliRunner

from platform_cli.client import ApiClient
from platform_cli.main import app, set_client_factory

runner = CliRunner()

CATALOG = [
    {
        "type": "s3-bucket",
        "display_name": "S3 bucket",
        "description": "Private object storage.",
        "provider": "aws",
        "approval_required": True,
        "environments": ["local", "dev"],
        "inputs": {},
    }
]

REQUEST = {
    "id": "r-abc123",
    "type": "s3-bucket",
    "environment": "local",
    "inputs": {"name": "demo-uploads", "team": "web", "cost_center": "cc-100"},
    "requested_by": "asaf",
    "state": "pr-opened",
    "created_at": "2026-10-24T20:00:00+00:00",
    "updated_at": "2026-10-24T20:00:01+00:00",
    "branch": "request/r-abc123",
    "pr_number": 7,
    "pr_url": "https://github.com/asaf-1/DevOps-Platform/pull/7",
    "outputs": None,
    "error": None,
}

EVENTS = [
    {
        "id": 1,
        "request_id": "r-abc123",
        "event": "requested",
        "actor": "asaf",
        "actor_type": "human",
        "at": "2026-10-24T20:00:00+00:00",
        "details": {},
    },
    {
        "id": 2,
        "request_id": "r-abc123",
        "event": "pr-opened",
        "actor": "platform-api",
        "actor_type": "system",
        "at": "2026-10-24T20:00:01+00:00",
        "details": {"pr_url": REQUEST["pr_url"]},
    },
]


@pytest.fixture(autouse=True)
def fake_api():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        path = request.url.path
        if path == "/catalog":
            return httpx.Response(200, json=CATALOG)
        if path == "/requests" and request.method == "POST":
            body = json.loads(request.content)
            if body["inputs"].get("name") == "BAD":
                return httpx.Response(422, json={"detail": "invalid inputs: name"})
            return httpx.Response(201, json={**REQUEST, "inputs": body["inputs"]})
        if path == "/requests/r-abc123":
            return httpx.Response(200, json=REQUEST)
        if path == "/audit":
            return httpx.Response(200, json=EVENTS)
        return httpx.Response(404, json={"detail": "nope"})

    transport = httpx.MockTransport(handler)
    set_client_factory(lambda: ApiClient("http://api.test", transport=transport))
    yield calls
    set_client_factory(ApiClient)


def test_catalog_list() -> None:
    result = runner.invoke(app, ["catalog", "list"])
    assert result.exit_code == 0, result.output
    assert "s3-bucket" in result.output
    assert "required" in result.output


def test_request_sends_inputs_and_prints_pr(fake_api) -> None:
    result = runner.invoke(
        app,
        [
            "request",
            "s3-bucket",
            "--name",
            "demo-uploads",
            "--team",
            "web",
            "--cost-center",
            "cc-100",
            "-i",
            "retention=30d",
            "-i",
            "versioning=false",
            "--as",
            "asaf",
        ],
    )
    assert result.exit_code == 0, result.output
    sent = json.loads([c for c in fake_api if c.method == "POST"][0].content)
    assert sent["inputs"] == {
        "name": "demo-uploads",
        "team": "web",
        "cost_center": "cc-100",
        "retention": "30d",
        "versioning": False,
    }
    assert sent["requested_by"] == "asaf"
    assert "request r-abc123" in result.output
    assert "pull/7" in result.output
    assert "platform status r-abc123" in result.output


def test_request_error_is_reported() -> None:
    result = runner.invoke(
        app, ["request", "s3-bucket", "--name", "BAD", "--team", "web", "--cost-center", "cc-100"]
    )
    assert result.exit_code == 1
    assert "invalid inputs" in result.output


def test_status_shows_timeline() -> None:
    result = runner.invoke(app, ["status", "r-abc123"])
    assert result.exit_code == 0, result.output
    assert "state: pr-opened" in result.output
    assert "requested" in result.output and "pr-opened" in result.output
    assert "asaf (human)" in result.output
    assert "platform-api (system)" in result.output
