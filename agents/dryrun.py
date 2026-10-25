"""Dry run: the real agent (prompt, runbooks, model settings) against stub
tools. No cluster, no GitHub, no MCP servers: the stubs return canned
outputs for a broken demo app and print what the model sends them.

Use it to see what the model actually does, step by step, before a live
run. Takes a few minutes on a CPU model.

    cd agents && OLLAMA_BASE_URL=http://host.docker.internal:11434 \\
        MODEL_NAME=qwen3:4b-instruct-2507 .venv/bin/python dryrun.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
os.environ.setdefault("AGENTS_DIR", str(HERE))

from pydantic_ai import Agent, FunctionToolset  # noqa: E402
from pydantic_ai.messages import (  # noqa: E402
    RetryPromptPart,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.usage import UsageLimits  # noqa: E402

from runtime.knowledge import Knowledge  # noqa: E402
from runtime.manifest import CapabilityMap, load_yaml  # noqa: E402
from runtime.providers import ModelConfig  # noqa: E402
from runtime.runner import IncidentReport, Runner, default_paths, load_agent  # noqa: E402

REPO = HERE.parent
FINGERPRINT = "dryrun01"
ALERT: dict[str, Any] = {
    "fingerprint": FINGERPRINT,
    "labels": {
        "alertname": "DemoAppImagePullBackOff",
        "severity": "critical",
        "namespace": "demo",
        "pod": "demo-app-6d8f9c7b5-x2k4q",
        "container": "demo-app",
        "deployment": "demo-app",
    },
    "annotations": {
        "summary": "demo-app pod cannot pull its image",
        "description": "Pod demo/demo-app-6d8f9c7b5-x2k4q has been in ImagePullBackOff for 2m.",
    },
}

IMG = "ghcr.io/asaf-1/devops-platform/demo-app:does-not-exist"
DESCRIBE = f"""Name:             demo-app-6d8f9c7b5-x2k4q
Namespace:        demo
Node:             platform-control-plane/172.18.0.2
Labels:           app.kubernetes.io/name=demo-app
Status:           Pending
Controlled By:    ReplicaSet/demo-app-6d8f9c7b5
Containers:
  demo-app:
    Image:          {IMG}
    Port:           8080/TCP
    State:          Waiting
      Reason:       ImagePullBackOff
    Ready:          False
    Limits:
      memory:  16Mi
    Requests:
      cpu:     10m
      memory:  16Mi
Conditions:
  Type              Status
  Ready             False
  ContainersReady   False
Events:
  Type     Reason   Age               From     Message
  ----     ------   ---               ----     -------
  Normal   Pulling  2m (x4 over 3m)   kubelet  Pulling image "{IMG}"
  Warning  Failed   2m (x4 over 3m)   kubelet  Failed to pull image "{IMG}": not found
  Warning  Failed   2m (x4 over 3m)   kubelet  Error: ErrImagePull
  Normal   BackOff  1m (x6 over 3m)   kubelet  Back-off pulling image "{IMG}"
  Warning  Failed   1m (x6 over 3m)   kubelet  Error: ImagePullBackOff
"""

BROKEN_DEPLOYMENT = (REPO / "gitops/apps/demo-app/deployment.yaml").read_text(encoding="utf-8")
if "does-not-exist" not in BROKEN_DEPLOYMENT:
    BROKEN_DEPLOYMENT = (
        BROKEN_DEPLOYMENT.replace(":sha-d38fccf", ":does-not-exist")
        .replace("memory: 32Mi", "memory: 16Mi")
        .replace("memory: 64Mi", "memory: 16Mi")
    )

T0 = time.monotonic()


def t() -> str:
    return f"[{time.monotonic() - T0:6.0f}s]"


def kubectl_get(resourceType: str, namespace: str, name: str = "", output: str = "") -> str:  # noqa: N803
    """Get Kubernetes resources (like kubectl get)."""
    return (
        "NAME                        READY   STATUS             RESTARTS   AGE\n"
        "demo-app-6d8f9c7b5-x2k4q    0/1     ImagePullBackOff   0          3m\n"
    )


def kubectl_describe(resourceType: str, name: str, namespace: str) -> str:  # noqa: N803
    """Describe a Kubernetes resource (like kubectl describe)."""
    return DESCRIBE


def kubectl_logs(resourceType: str, name: str, namespace: str, container: str = "") -> str:  # noqa: N803
    """Get logs from a pod (like kubectl logs)."""
    return (
        "Error from server (BadRequest): container demo-app is waiting to start: "
        "image cannot be pulled"
    )


def get_file_contents(owner: str, repo: str, path: str, ref: str = "main") -> str:
    """Get the contents of a file from a GitHub repository."""
    if path.strip("/") == "gitops/apps/demo-app/deployment.yaml":
        return BROKEN_DEPLOYMENT
    return f"404 Not Found: {path}"


def create_branch(owner: str, repo: str, branch: str, from_branch: str = "main") -> str:
    """Create a new branch in a GitHub repository."""
    return json.dumps({"ref": f"refs/heads/{branch}", "from": from_branch})


def replace_line(path: str, find: str, replace: str, branch: str, message: str) -> str:
    """Change one line of a file in the GitOps repo, on an agent branch."""
    print(f"{t()}   >>> replace_line {path} on {branch}: {find!r} -> {replace!r} ({message})")
    lines = BROKEN_DEPLOYMENT.split("\n")
    hits = [i for i, line in enumerate(lines) if find in line]
    if not path.startswith("gitops/apps/") or not branch.startswith("agent/"):
        return "replace_line refused: path must be under gitops/apps/ and branch under agent/"
    if len(hits) != 1:
        return f"replace_line failed: {find!r} is on {len(hits)} lines"
    old = lines[hits[0]]
    new = old.replace(find, replace)
    return (
        f"changed line {hits[0] + 1} of {path} on {branch} (commit abc1234):\n"
        f"- {old.strip()}\n+ {new.strip()}"
    )


def create_pull_request(
    owner: str, repo: str, title: str, head: str, base: str, body: str = ""
) -> str:
    """Create a new pull request in a GitHub repository."""
    print(f"{t()}   >>> PR {title!r} {head} -> {base}, body {len(body)} chars")
    return json.dumps({"number": 999, "html_url": f"https://github.com/{owner}/{repo}/pull/999"})


def show_response(resp: Any) -> None:
    for part in resp.parts:
        if isinstance(part, ThinkingPart):
            print(f"{t()} model THINKING {len(part.content)} chars")
        elif isinstance(part, TextPart):
            print(f"{t()} model TEXT ({len(part.content)} chars): {part.content[:300]!r}")
        elif isinstance(part, ToolCallPart):
            args = part.args if isinstance(part.args, str) else json.dumps(part.args)
            print(f"{t()} model TOOL {part.tool_name}({args[:220]})")
    u = resp.usage
    print(f"{t()}   usage: in={u.input_tokens} out={u.output_tokens}")


def show_request(req: Any) -> None:
    for part in req.parts:
        if isinstance(part, ToolReturnPart):
            c = part.content if isinstance(part.content, str) else json.dumps(part.content)
            print(f"{t()} tool RETURN {part.tool_name}: {c[:120]!r}...")
        elif isinstance(part, RetryPromptPart):
            c = part.content if isinstance(part.content, str) else json.dumps(part.content)
            print(f"{t()} RETRY prompt: {c[:200]!r}")


async def main() -> None:
    agents_dir, runbooks_dir, agent_dir = default_paths()
    capmap = CapabilityMap.load(
        agents_dir / "tools" / "capabilities.yaml", agents_dir / "tools" / "mcp.yaml"
    )
    spec = load_agent(agent_dir, capmap)
    knowledge = Knowledge.load(runbooks_dir)
    cfg = ModelConfig.from_env()
    runner = Runner(
        None,  # type: ignore[arg-type]  # no audit store in a dry run
        spec,
        load_yaml(agents_dir / "tools" / "mcp.yaml"),
        knowledge,
        model_cfg=cfg,
    )
    m = spec.manifest

    toolsets = [
        FunctionToolset(tools=[kubectl_get, kubectl_describe, kubectl_logs]).prefixed("kubernetes"),
        FunctionToolset(tools=[get_file_contents, create_branch, create_pull_request]).prefixed(
            "github"
        ),
        FunctionToolset(tools=[replace_line]).prefixed("local"),
    ]
    instructions = runner.instructions(ALERT)
    print(f"model: {cfg.provider}:{cfg.name} at {cfg.ollama_base_url}")
    print(
        f"instructions: {len(instructions)} chars, max_steps={m.max_steps}, "
        f"token_budget={m.token_budget}"
    )
    agent: Agent[None, IncidentReport] = Agent(
        runner.model,
        name=m.name,
        instructions=instructions,
        toolsets=toolsets,
        output_type=IncidentReport,
        retries=2,
    )
    limits = UsageLimits(request_limit=m.max_steps, total_tokens_limit=m.token_budget)
    try:
        async with agent.iter(runner.user_prompt(ALERT, FINGERPRINT), usage_limits=limits) as run:
            async for node in run:
                if Agent.is_call_tools_node(node):
                    show_response(node.model_response)
                elif Agent.is_model_request_node(node):
                    show_request(node.request)
                elif Agent.is_end_node(node):
                    print(f"{t()} END")
        result = run.result
    except Exception as e:  # noqa: BLE001
        print(f"{t()} FAILED: {type(e).__name__}: {str(e)[:500]}")
        return
    assert result is not None
    print(f"{t()} usage total: {result.usage()}")
    print("=== REPORT ===")
    out = result.output
    print(out.markdown() if isinstance(out, IncidentReport) else out)


if __name__ == "__main__":
    asyncio.run(main())
