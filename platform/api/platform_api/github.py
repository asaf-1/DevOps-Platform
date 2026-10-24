"""The small slice of the GitHub REST API the platform uses.

Branch, one file commit, pull request. Uses the fine-grained token in
PLATFORM_GITHUB_TOKEN (Contents RW, Pull requests RW, Metadata R), never
the built-in GITHUB_TOKEN, so the PR triggers its own CI run.
"""

from __future__ import annotations

import base64
from typing import Any, Protocol

import httpx


class GitHubError(RuntimeError):
    pass


class PullRequestInfo(dict[str, Any]):
    """Plain dict with number, html_url, head sha and so on."""

    @property
    def number(self) -> int:
        return int(self["number"])

    @property
    def html_url(self) -> str:
        return str(self["html_url"])


class GitHub(Protocol):
    """What the API needs from GitHub. The tests use a fake; production uses GitHubClient."""

    def create_branch_with_file(
        self, branch: str, path: str, content: str, message: str
    ) -> str: ...

    def open_pull_request(
        self, title: str, body: str, head: str, labels: list[str]
    ) -> PullRequestInfo: ...


class GitHubClient:
    def __init__(
        self,
        repo: str,
        token: str,
        *,
        base_branch: str = "main",
        api_url: str = "https://api.github.com",
        timeout: float = 20.0,
    ) -> None:
        self.repo = repo
        self.base_branch = base_branch
        self._client = httpx.Client(
            base_url=f"{api_url}/repos/{repo}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=timeout,
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        resp = self._client.request(method, path, **kwargs)
        if resp.status_code >= 400:
            raise GitHubError(f"{method} {path} -> {resp.status_code}: {resp.text[:300]}")
        return resp.json() if resp.content else None

    # branches and commits

    def base_sha(self) -> str:
        data = self._request("GET", f"/git/ref/heads/{self.base_branch}")
        return str(data["object"]["sha"])

    def create_branch_with_file(self, branch: str, path: str, content: str, message: str) -> str:
        """Create branch from the base branch and commit one file on it. Returns the commit sha."""
        sha = self.base_sha()
        self._request("POST", "/git/refs", json={"ref": f"refs/heads/{branch}", "sha": sha})
        data = self._request(
            "PUT",
            f"/contents/{path}",
            json={
                "message": message,
                "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
                "branch": branch,
            },
        )
        return str(data["commit"]["sha"])

    # pull requests

    def open_pull_request(
        self, title: str, body: str, head: str, labels: list[str]
    ) -> PullRequestInfo:
        pr = self._request(
            "POST",
            "/pulls",
            json={"title": title, "body": body, "head": head, "base": self.base_branch},
        )
        if labels:
            self._request("POST", f"/issues/{pr['number']}/labels", json={"labels": labels})
        return PullRequestInfo(pr)

    def get_pull_request(self, number: int) -> PullRequestInfo:
        return PullRequestInfo(self._request("GET", f"/pulls/{number}"))

    def list_pull_requests(
        self, *, state: str = "closed", label: str | None = None
    ) -> list[PullRequestInfo]:
        """Closed PRs with a label, newest first. The worker checks merged_at itself."""
        params: dict[str, Any] = {
            "state": state,
            "per_page": 50,
            "sort": "updated",
            "direction": "desc",
        }
        prs = self._request("GET", "/pulls", params=params) or []
        if label:
            prs = [p for p in prs if any(lb.get("name") == label for lb in p.get("labels", []))]
        return [PullRequestInfo(p) for p in prs]

    def workflow_run_conclusion(self, workflow_file: str, head_sha: str) -> str | None:
        """Conclusion of the latest run of a workflow for a commit, or None if no run yet."""
        data = self._request(
            "GET",
            f"/actions/workflows/{workflow_file}/runs",
            params={"head_sha": head_sha, "per_page": 5},
        )
        runs = (data or {}).get("workflow_runs", [])
        if not runs:
            return None
        return runs[0].get("conclusion")

    def get_file(self, path: str, ref: str) -> tuple[str, str]:
        """Return (content, blob sha) of a file at a ref."""
        data = self._request("GET", f"/contents/{path}", params={"ref": ref})
        content = base64.b64decode(data["content"]).decode("utf-8")
        return content, str(data["sha"])

    def put_file(self, path: str, content: str, message: str, branch: str, sha: str | None) -> str:
        payload: dict[str, Any] = {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "branch": branch,
        }
        if sha:
            payload["sha"] = sha
        data = self._request("PUT", f"/contents/{path}", json=payload)
        return str(data["commit"]["sha"])
