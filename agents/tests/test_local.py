"""replace_line: one line in, one line out, against a fake GitHub API."""

import base64
import json
from collections.abc import Callable
from typing import Any

import httpx

from runtime.tools.local import make_local_toolset

PATH = "gitops/apps/demo-app/deployment.yaml"
BRANCH = "agent/incident-1"
FILE = (
    "kind: Deployment\n"
    "          image: ghcr.io/x/demo-app:does-not-exist\n"
    "  memory: 16Mi\n"
    "  memory: 16Mi\n"
)


def fake_github(store: dict[str, Any]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path.endswith(f"/contents/{PATH}"):
            if request.url.params.get("ref") != BRANCH:
                return httpx.Response(404, json={"message": "Not Found"})
            content = base64.b64encode(store["file"].encode()).decode()
            return httpx.Response(200, json={"sha": "f00", "content": content})
        if request.method == "PUT" and request.url.path.endswith(f"/contents/{PATH}"):
            body = json.loads(request.content)
            store["put"] = body
            store["file"] = base64.b64decode(body["content"]).decode()
            return httpx.Response(200, json={"commit": {"sha": "abc1234def"}})
        return httpx.Response(404, json={"message": "Not Found"})

    return httpx.Client(base_url="https://api.github.com", transport=httpx.MockTransport(handler))


def tool(store: dict[str, Any]) -> Callable[..., str]:
    ts = make_local_toolset("x/y", "tok", client=fake_github(store))
    return ts.tools["replace_line"].function  # type: ignore[no-any-return]


def test_changes_exactly_one_line() -> None:
    store: dict[str, Any] = {"file": FILE}
    out = tool(store)(PATH, "demo-app:does-not-exist", "demo-app:main", BRANCH, "[agent] fix tag")
    assert out.startswith("changed line 2 of")
    assert "- image: ghcr.io/x/demo-app:does-not-exist" in out
    assert "+ image: ghcr.io/x/demo-app:main" in out
    assert store["file"] == FILE.replace("does-not-exist", "main")
    assert store["put"]["sha"] == "f00" and store["put"]["branch"] == BRANCH
    assert store["put"]["message"] == "[agent] fix tag"


def test_refuses_wrong_path_and_branch() -> None:
    store: dict[str, Any] = {"file": FILE}
    assert "refused" in tool(store)("apps/demo-app/deployment.yaml", "a", "b", BRANCH, "m")
    assert "refused" in tool(store)(PATH, "a", "b", "main", "m")
    assert "put" not in store


def test_refuses_multiline_find_with_guidance() -> None:
    store: dict[str, Any] = {"file": FILE}
    out = tool(store)(PATH, "a\nb", "c", BRANCH, "m")
    assert out.startswith("replace_line refused") and "ONE line" in out
    assert "put" not in store


def test_reports_missing_and_ambiguous_lines() -> None:
    store: dict[str, Any] = {"file": FILE}
    assert "no line of" in tool(store)(PATH, "sha-1234567", "main", BRANCH, "m")
    out = tool(store)(PATH, "memory: 16Mi", "memory: 64Mi", BRANCH, "m")
    assert "is on 2 lines" in out
    assert "put" not in store
