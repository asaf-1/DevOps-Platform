"""Build the agent's toolsets and guard every call.

Order of wrapping, per server:
    MCPToolset -> filtered(allowlist) -> GuardedToolset -> prefixed(server)
so the model sees `kubernetes_kubectl_get`, the allowlist speaks of
`kubernetes.kubectl_get`, and GuardedToolset.call_tool is the single place
that checks namespace scope and branch rules, writes the audit event and
opens the OpenTelemetry span.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any

from opentelemetry import trace
from pydantic_ai import RunContext
from pydantic_ai.toolsets import AbstractToolset, FunctionToolset, WrapperToolset

from ..audit import Store
from ..manifest import AgentManifest, _expand_env

PREVIEW_CHARS = 400
BASE_BRANCH = os.environ.get("GITHUB_BASE_BRANCH", "main")

_NS_FLAG = re.compile(r"(?:^|\s)(?:-n|--namespace)[\s=]+([a-z0-9-]+)")
_ALL_NS = re.compile(r"(?:^|\s)(?:-A|--all-namespaces)(?:\s|$)")


@dataclass
class ToolCallRecord:
    tool: str
    args: dict[str, Any]
    ok: bool
    duration_ms: int
    preview: str
    refused: str | None = None
    step: int | None = None


@dataclass
class ToolGuard:
    """Per-run policy and bookkeeping shared by every toolset of the run."""

    allowed_tools: set[str]
    allowed_namespaces: set[str]
    agent: str
    run_id: str
    store: Store | None = None
    records: list[ToolCallRecord] = field(default_factory=list)

    # policy

    def check(self, qualified: str, args: dict[str, Any]) -> str | None:
        """Refusal reason, or None when the call may proceed."""
        if qualified not in self.allowed_tools:
            return f"{qualified} is not in this agent's allowlist"
        server = qualified.split(".", 1)[0]
        if server == "kubernetes":
            return self._check_namespace(args)
        if server == "github":
            return self._check_github(qualified, args)
        return None

    def _check_namespace(self, args: dict[str, Any]) -> str | None:
        allowed = ", ".join(sorted(self.allowed_namespaces))
        found: set[str] = set()
        for key in ("namespace", "ns"):
            if args.get(key):
                found.add(str(args[key]))
        for value in args.values():
            if isinstance(value, str):
                if _ALL_NS.search(value):
                    return f"all-namespaces is not allowed; use one of: {allowed}"
                for m in _NS_FLAG.finditer(value):
                    found.add(m.group(1))
        if not found:
            return f"a namespace is required; use one of: {allowed}"
        bad = found - self.allowed_namespaces
        if bad:
            return f"namespace {', '.join(sorted(bad))} is outside this agent's scope ({allowed})"
        return None

    def _check_github(self, qualified: str, args: dict[str, Any]) -> str | None:
        branch = str(args.get("branch") or args.get("head") or "")
        if qualified.endswith(("create_branch", "create_or_update_file", "push_files")):
            if not branch.startswith("agent/"):
                return f"writes are only allowed on branches named agent/*, got {branch!r}"
        if qualified.endswith("create_pull_request"):
            base = str(args.get("base") or "")
            if base and base != BASE_BRANCH:
                return f"pull requests must target {BASE_BRANCH}, got {base!r}"
            if not branch.startswith("agent/"):
                return f"pull request head must be an agent/* branch, got {branch!r}"
        if branch == BASE_BRANCH:
            return f"direct changes to {BASE_BRANCH} are never allowed"
        return None

    # bookkeeping

    def record(self, rec: ToolCallRecord) -> None:
        self.records.append(rec)
        if self.store is not None:
            self.store.add_step(self.run_id, rec.__dict__)
            self.store.audit(
                "agent.tool_call" if rec.refused is None else "agent.tool_refused",
                actor=self.agent,
                actor_type="agent",
                details={
                    "run_id": self.run_id,
                    "tool": rec.tool,
                    "args": _truncate(json.dumps(rec.args, default=str), PREVIEW_CHARS),
                    "ok": rec.ok,
                    "duration_ms": rec.duration_ms,
                    **({"refused": rec.refused} if rec.refused else {}),
                },
            )


def _truncate(text: str, n: int) -> str:
    return text if len(text) <= n else text[: n - 3] + "..."


def _preview(result: Any) -> str:
    try:
        text = result if isinstance(result, str) else json.dumps(result, default=str)
    except TypeError:
        text = str(result)
    return _truncate(text, PREVIEW_CHARS)


class GuardedToolset(WrapperToolset[Any]):
    """The one wrapper. Refusals and tool errors go back to the model as text, so it can adapt."""

    def __init__(self, wrapped: AbstractToolset[Any], server: str, guard: ToolGuard) -> None:
        super().__init__(wrapped)
        self.server = server
        self.guard = guard

    @property
    def id(self) -> str | None:
        return f"guarded-{self.server}"

    async def call_tool(
        self, name: str, tool_args: dict[str, Any], ctx: RunContext[Any], tool: Any
    ) -> Any:
        qualified = f"{self.server}.{name}"
        step = getattr(ctx, "run_step", None)
        reason = self.guard.check(qualified, tool_args)
        if reason is not None:
            self.guard.record(
                ToolCallRecord(qualified, tool_args, False, 0, "", refused=reason, step=step)
            )
            return f"REFUSED: {reason}"
        tracer = trace.get_tracer("agent-runtime")
        started = time.monotonic()
        with tracer.start_as_current_span(f"tool {qualified}") as span:
            span.set_attribute("tool.name", qualified)
            span.set_attribute(
                "tool.args", _truncate(json.dumps(tool_args, default=str), PREVIEW_CHARS)
            )
            try:
                result = await super().call_tool(name, tool_args, ctx, tool)
            except Exception as e:
                # A failing tool is information, not the end of the run: the
                # model reads the error and adapts (another resource, an
                # existing branch). Same shape as a refusal.
                ms = int((time.monotonic() - started) * 1000)
                span.record_exception(e)
                message = _truncate(f"{type(e).__name__}: {e}", PREVIEW_CHARS)
                self.guard.record(
                    ToolCallRecord(qualified, tool_args, False, ms, message, step=step)
                )
                return f"ERROR: {message}"
        ms = int((time.monotonic() - started) * 1000)
        self.guard.record(
            ToolCallRecord(qualified, tool_args, True, ms, _preview(result), step=step)
        )
        return result


def _mcp_toolset(server: str, spec: dict[str, Any]) -> AbstractToolset[Any]:
    """An MCPToolset over a stdio subprocess, built lazily so tests need no servers."""
    from fastmcp import Client
    from fastmcp.client.transports import StdioTransport
    from pydantic_ai.mcp import MCPToolset

    env = {k: _expand_env(str(v)) for k, v in (spec.get("env") or {}).items()}
    transport = StdioTransport(
        command=str(spec["command"]),
        args=[str(a) for a in spec.get("args") or []],
        env={**os.environ, **env},
    )
    return MCPToolset(Client(transport), id=server, tool_error_behavior="error")


def wrap(toolset: AbstractToolset[Any], server: str, guard: ToolGuard) -> AbstractToolset[Any]:
    """filtered(allowlist) -> guarded -> prefixed(server)."""
    allowed = guard.allowed_tools

    def allow(ctx: RunContext[Any], tool_def: Any) -> bool:
        return f"{server}.{tool_def.name}" in allowed

    return GuardedToolset(toolset.filtered(allow), server, guard).prefixed(server)


def build_toolsets(
    mcp_doc: dict[str, Any],
    manifest: AgentManifest,
    guard: ToolGuard,
    local_tools: FunctionToolset[Any] | None = None,
    fixture: Any | None = None,
) -> list[AbstractToolset[Any]]:
    """One wrapped toolset per MCP server the agent actually uses, plus local tools.

    With a fixture (given, or `EVAL_MODE=1` with `EVAL_FIXTURE=<yaml>`) the
    tools are served from the fixture instead of the MCP servers; the guard
    in front of them is the same.
    """
    used_servers = {t.split(".", 1)[0] for t in manifest.allowed_tools}
    if fixture is None and os.environ.get("EVAL_MODE") == "1":
        from .fixture import Fixture

        fixture = Fixture.load(os.environ["EVAL_FIXTURE"])
    if fixture is not None:
        from .fixture import build_fixture_toolsets

        return [
            wrap(ts, server, guard)
            for server, ts in build_fixture_toolsets(fixture, used_servers).items()
        ]
    toolsets: list[AbstractToolset[Any]] = []
    for server, spec in (mcp_doc.get("servers") or {}).items():
        if server not in used_servers:
            continue
        toolsets.append(wrap(_mcp_toolset(server, spec), server, guard))
    if local_tools is not None and "local" in used_servers:
        toolsets.append(wrap(local_tools, "local", guard))
    return toolsets
