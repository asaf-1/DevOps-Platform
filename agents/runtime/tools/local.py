"""Small local tools that need no MCP server.

`replace_line` is shaped for small models: the agent names one line and
its replacement, the runtime reads the file, edits that line and commits.
The model never has to reproduce a whole file, which a 4B model on a CPU
gets wrong (wrong path, dropped settings) and which costs minutes of
output.
"""

from __future__ import annotations

import base64
import os
from typing import Any

import httpx
from pydantic_ai.toolsets import FunctionToolset

GITOPS_PREFIX = "gitops/apps/"
BRANCH_PREFIX = "agent/"


def make_local_toolset(
    repo: str | None = None, token: str | None = None, client: httpx.Client | None = None
) -> FunctionToolset[Any]:
    repo = repo or os.environ.get("GITHUB_REPO", "asaf-1/DevOps-Platform")
    token = token or os.environ.get("PLATFORM_GITHUB_TOKEN", "")
    base_branch = os.environ.get("GITHUB_BASE_BRANCH", "main")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    api = client or httpx.Client(base_url="https://api.github.com", headers=headers, timeout=20)

    def git_log(path: str, limit: int = 10) -> str:
        """Recent commits on the main branch that touched a path in the GitOps repo.

        Args:
            path: repository path, e.g. gitops/apps/demo-app/deployment.yaml
            limit: how many commits, newest first (max 30)
        """
        limit = max(1, min(int(limit), 30))
        resp = api.get(
            f"/repos/{repo}/commits",
            params={"path": path, "per_page": limit, "sha": base_branch},
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

    def replace_line(path: str, find: str, replace: str, branch: str, message: str) -> str:
        """Change one line of a file in the GitOps repo, on an agent branch.

        The runtime reads the file, replaces `find` on the single line that
        contains it with `replace`, and commits. You never write whole files.

        Args:
            path: file in the GitOps repo, e.g. gitops/apps/demo-app/deployment.yaml
            find: text that appears on exactly one line, copied from the file,
                e.g. demo-app:does-not-exist
            replace: what that text becomes, e.g. demo-app:main
            branch: the agent branch to commit on, e.g. agent/incident-<fingerprint>
            message: commit message, e.g. "[agent] demo-app: image tag does-not-exist -> main"
        """
        path = path.strip().lstrip("/")
        if not path.startswith(GITOPS_PREFIX):
            return (
                f"replace_line refused: only files under {GITOPS_PREFIX} may change, not {path!r}"
            )
        if not branch.startswith(BRANCH_PREFIX):
            return f"replace_line refused: branch must start with {BRANCH_PREFIX}, not {branch!r}"
        if not find or find == replace:
            return "replace_line refused: find must be non-empty and differ from replace"
        resp = api.get(f"/repos/{repo}/contents/{path}", params={"ref": branch})
        if resp.status_code == 404:
            return (
                f"replace_line failed: {path} not found on branch {branch}; "
                "an app's GitOps file is gitops/apps/<app>/deployment.yaml"
            )
        if resp.status_code != 200:
            return f"replace_line failed: HTTP {resp.status_code} {resp.text[:200]}"
        meta = resp.json()
        text = base64.b64decode(meta["content"]).decode("utf-8")
        lines = text.split("\n")
        hits = [i for i, line in enumerate(lines) if find in line]
        if not hits:
            return (
                f"replace_line failed: no line of {path} contains {find!r}; "
                "copy the exact text from get_file_contents"
            )
        if len(hits) > 1:
            shown = "; ".join(f"line {i + 1}: {lines[i].strip()}" for i in hits[:5])
            return f"replace_line failed: {find!r} is on {len(hits)} lines ({shown}); be specific"
        i = hits[0]
        old = lines[i]
        lines[i] = old.replace(find, replace)
        new_text = "\n".join(lines)
        put = api.put(
            f"/repos/{repo}/contents/{path}",
            json={
                "message": message,
                "content": base64.b64encode(new_text.encode("utf-8")).decode("ascii"),
                "sha": meta["sha"],
                "branch": branch,
            },
        )
        if put.status_code not in (200, 201):
            return f"replace_line failed: HTTP {put.status_code} {put.text[:200]}"
        sha = str((put.json().get("commit") or {}).get("sha", ""))[:7]
        return (
            f"changed line {i + 1} of {path} on {branch} (commit {sha}):\n"
            f"- {old.strip()}\n+ {lines[i].strip()}"
        )

    platform_api = os.environ.get(
        "PLATFORM_API_URL", "http://platform-api.platform.svc.cluster.local"
    )

    def smoke_test(app: str) -> str:
        """Run the platform's smoke test of an application and report pass or fail per step.

        Read-only: the platform API calls the app's own health, products and
        orders endpoints (what its sanity test checks). Use it to confirm a
        diagnosis or to check that an app is really broken.

        Args:
            app: the application to test, e.g. bank or demo-app
        """
        try:
            resp = api.get(f"{platform_api}/smoke/{app}", timeout=90)
        except httpx.HTTPError as e:
            return f"smoke_test failed: {e}"
        if resp.status_code != 200:
            return f"smoke_test failed: HTTP {resp.status_code} {resp.text[:200]}"
        data = resp.json()
        lines = [
            f"{app}: {'PASS' if data.get('passed') else 'FAIL'} ({data.get('duration_ms')} ms)"
        ]
        for step in data.get("steps", []):
            mark = "ok " if step.get("ok") else "FAIL"
            lines.append(f"  {mark} {step.get('name')}: {step.get('detail', '')}")
        return "\n".join(lines)

    return FunctionToolset([git_log, replace_line, smoke_test], id="local")
