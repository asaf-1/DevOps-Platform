"""Fixture-backed tools for evals and dry runs.

A fixture is one YAML file: the alert, the GitOps files the agent may read
and change, canned outputs for the cluster tools, and what a good run looks
like (`expect`). With `EVAL_MODE=1` (or an explicit fixture) the registry
builds these tools instead of the MCP servers, so an eval needs no cluster,
no GitHub and no network, and the same guard still sits in front of every
call. The tools mirror the real ones' names and arguments, so the model sees
the same schemas it sees in production.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_ai.toolsets import FunctionToolset

GITOPS_PREFIX = "gitops/apps/"
BRANCH_PREFIX = "agent/"


class ToolResponse(BaseModel):
    """One canned output; `when` maps argument names to substrings that must appear."""

    when: dict[str, str] = Field(default_factory=dict)
    returns: str = ""


class Expect(BaseModel):
    """What a good run looks like. Checked by `runtime.evalrun.verdict`."""

    keywords: list[str] = Field(default_factory=list)  # all must appear in the report
    keywords_any: list[str] = Field(default_factory=list)  # at least one must appear
    changed_file: str | None = None  # the one file replace_line must touch
    replace_contains: str | None = None  # substring of the replacement text
    no_change: bool = False  # the agent must not change any file
    pr: bool = False  # a pull request must be opened
    forbidden_tools: list[str] = Field(default_factory=list)  # never called, even refused
    max_steps: int = 10  # tool calls, at most
    status: str = "done"  # run status expected (done, failed)
    cite_evidence: bool = True  # evidence bullets must quote a tool output


class Fixture(BaseModel):
    name: str
    description: str = ""
    alert: dict[str, Any]
    files: dict[str, str] = Field(default_factory=dict)
    tools: dict[str, list[ToolResponse]] = Field(default_factory=dict)
    overrides: dict[str, int] = Field(default_factory=dict)  # max_steps, token_budget
    expect: Expect = Field(default_factory=Expect)
    proposals: dict[str, list[dict[str, Any]]] = Field(
        default_factory=lambda: {"branches": [], "changes": [], "prs": []}
    )

    @classmethod
    def load(cls, path: str | Path) -> Fixture:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        return cls.model_validate(data)

    def tool_outputs(self) -> str:
        """Everything a tool could have returned, for the cite-evidence check."""
        parts = [r.returns for rs in self.tools.values() for r in rs]
        parts += list(self.files.values())
        return "\n".join(parts)

    def response(self, tool: str, args: dict[str, Any]) -> str:
        for r in self.tools.get(tool, []):
            if all(v in str(args.get(k, "")) for k, v in r.when.items()):
                return r.returns
        return (
            f"ERROR: nothing recorded for {tool} with {json.dumps(args, default=str)[:160]}; "
            "use another tool or report what you could not verify"
        )


def build_fixture_toolsets(fixture: Fixture, servers: set[str]) -> dict[str, FunctionToolset[Any]]:
    """One FunctionToolset per server the agent uses, serving the fixture."""

    def kubectl_get(resourceType: str, namespace: str, name: str = "", output: str = "") -> str:  # noqa: N803
        """Get Kubernetes resources (like kubectl get).

        Args:
            resourceType: pods, deployments, services, configmaps, events, nodes ...
            namespace: the namespace to look in
            name: one resource, or empty for all
            output: optional output format such as yaml or wide
        """
        return fixture.response(
            "kubernetes.kubectl_get",
            {"resourceType": resourceType, "namespace": namespace, "name": name, "output": output},
        )

    def kubectl_describe(resourceType: str, name: str, namespace: str) -> str:  # noqa: N803
        """Describe a Kubernetes resource (like kubectl describe).

        Args:
            resourceType: pod, deployment, service, node ...
            name: the resource name
            namespace: the namespace it lives in
        """
        return fixture.response(
            "kubernetes.kubectl_describe",
            {"resourceType": resourceType, "name": name, "namespace": namespace},
        )

    def kubectl_logs(resourceType: str, name: str, namespace: str, container: str = "") -> str:  # noqa: N803
        """Get logs from a pod (like kubectl logs).

        Args:
            resourceType: pod
            name: the pod name
            namespace: the namespace it lives in
            container: the container, when the pod has several
        """
        return fixture.response(
            "kubernetes.kubectl_logs",
            {
                "resourceType": resourceType,
                "name": name,
                "namespace": namespace,
                "container": container,
            },
        )

    def get_file_contents(owner: str, repo: str, path: str, ref: str = "main") -> str:
        """Get the contents of a file from a GitHub repository.

        Args:
            owner: repository owner
            repo: repository name
            path: file path in the repository
            ref: branch, tag or commit (default main)
        """
        key = path.strip().lstrip("/")
        if key in fixture.files:
            return fixture.files[key]
        return f"ERROR: 404 Not Found: {key} (ref {ref})"

    def create_branch(owner: str, repo: str, branch: str, from_branch: str = "main") -> str:
        """Create a new branch in a GitHub repository.

        Args:
            owner: repository owner
            repo: repository name
            branch: the new branch name
            from_branch: the branch to start from (default main)
        """
        fixture.proposals["branches"].append({"branch": branch, "from": from_branch})
        return json.dumps({"ref": f"refs/heads/{branch}", "from": from_branch})

    def create_pull_request(
        owner: str, repo: str, title: str, head: str, base: str, body: str = ""
    ) -> str:
        """Create a new pull request in a GitHub repository.

        Args:
            owner: repository owner
            repo: repository name
            title: pull request title
            head: the branch with the change
            base: the branch to merge into
            body: pull request description
        """
        number = 100 + len(fixture.proposals["prs"])
        url = f"https://github.com/{owner}/{repo}/pull/{number}"
        fixture.proposals["prs"].append(
            {"number": number, "title": title, "head": head, "base": base, "body": body, "url": url}
        )
        return json.dumps({"number": number, "html_url": url})

    def replace_line(path: str, find: str, replace: str, branch: str, message: str) -> str:
        """Change one line of a file in the GitOps repo, on an agent branch.

        The runtime reads the file, replaces `find` on the single line that
        contains it with `replace`, and commits. You never write whole files.

        Args:
            path: file in the GitOps repo, e.g. gitops/apps/demo-app/deployment.yaml
            find: text that appears on exactly one line, copied from the file
            replace: what that text becomes
            branch: the agent branch to commit on, e.g. agent/incident-<fingerprint>
            message: commit message
        """
        key = path.strip().lstrip("/")
        if not key.startswith(GITOPS_PREFIX):
            return f"replace_line refused: only files under {GITOPS_PREFIX} may change, not {key!r}"
        if not branch.startswith(BRANCH_PREFIX):
            return f"replace_line refused: branch must start with {BRANCH_PREFIX}, not {branch!r}"
        if not find or find == replace:
            return "replace_line refused: find must be non-empty and differ from replace"
        if key not in fixture.files:
            return (
                f"replace_line failed: {key} not found on branch {branch}; "
                "an app's GitOps file is gitops/apps/<app>/deployment.yaml"
            )
        lines = fixture.files[key].split("\n")
        hits = [i for i, line in enumerate(lines) if find in line]
        if not hits:
            return f"replace_line failed: no line of {key} contains {find!r}; copy the exact text"
        if len(hits) > 1:
            return f"replace_line failed: {find!r} is on {len(hits)} lines; be specific"
        i = hits[0]
        old = lines[i]
        lines[i] = old.replace(find, replace)
        fixture.files[key] = "\n".join(lines)
        fixture.proposals["changes"].append(
            {
                "path": key,
                "line": i + 1,
                "find": find,
                "replace": replace,
                "branch": branch,
                "message": message,
                "old": old.strip(),
                "new": lines[i].strip(),
            }
        )
        return (
            f"changed line {i + 1} of {key} on {branch} (commit f1x7ure):\n"
            f"- {old.strip()}\n+ {lines[i].strip()}"
        )

    def git_log(path: str, limit: int = 10) -> str:
        """Recent commits on the main branch that touched a path in the GitOps repo.

        Args:
            path: repository path
            limit: how many commits, newest first
        """
        return fixture.response("local.git_log", {"path": path, "limit": limit})

    by_server: dict[str, list[Any]] = {
        "kubernetes": [kubectl_get, kubectl_describe, kubectl_logs],
        "github": [get_file_contents, create_branch, create_pull_request],
        "local": [replace_line, git_log],
    }
    return {
        server: FunctionToolset(tools, id=f"fixture-{server}")
        for server, tools in by_server.items()
        if server in servers
    }
