"""Small local tools that need no MCP server."""

from __future__ import annotations

import os
from typing import Any

import httpx
from pydantic_ai.toolsets import FunctionToolset


def make_local_toolset(repo: str | None = None, token: str | None = None) -> FunctionToolset[Any]:
    repo = repo or os.environ.get("GITHUB_REPO", "asaf-1/DevOps-Platform")
    token = token or os.environ.get("PLATFORM_GITHUB_TOKEN", "")

    def git_log(path: str, limit: int = 10) -> str:
        """Recent commits on the main branch that touched a path in the GitOps repo.

        Args:
            path: repository path, e.g. gitops/apps/demo-app/deployment.yaml
            limit: how many commits, newest first (max 30)
        """
        limit = max(1, min(int(limit), 30))
        headers = {"Accept": "application/vnd.github+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        resp = httpx.get(
            f"https://api.github.com/repos/{repo}/commits",
            params={
                "path": path,
                "per_page": limit,
                "sha": os.environ.get("GITHUB_BASE_BRANCH", "main"),
            },
            headers=headers,
            timeout=20,
        )
        if resp.status_code != 200:
            return f"git_log failed: HTTP {resp.status_code} {resp.text[:200]}"
        lines = []
        for c in resp.json():
            sha = c["sha"][:7]
            when = c["commit"]["author"]["date"][:16].replace("T", " ")
            who = c["commit"]["author"]["name"]
            msg = c["commit"]["message"].split("\n")[0]
            lines.append(f"{sha} {when} {who}: {msg}")
        return "\n".join(lines) if lines else f"no commits touch {path}"

    return FunctionToolset([git_log], id="local")
