"""Run one agent against one alert.

Everything the agent may do is decided here from files: the manifest
(what), the capability map (what each tool is), the prompt (how), the
runbooks (knowledge). The model is whatever providers.build_model returns.
"""

from __future__ import annotations

import json
import logging
import os
import re
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from opentelemetry import trace
from opentelemetry.context import Context
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models import Model
from pydantic_ai.usage import UsageLimits

from .audit import Store
from .knowledge import Knowledge, alert_tags
from .manifest import (
    AgentManifest,
    CapabilityMap,
    describe,
    load_manifest,
    load_yaml,
    validate_manifest,
)
from .providers import ModelConfig, build_model
from .tools.local import make_local_toolset
from .tools.registry import ToolGuard, build_toolsets

log = logging.getLogger("agent.runner")

_PR_URL = re.compile(r"https://github\.com/[\w.-]+/[\w.-]+/pull/\d+")


class IncidentReport(BaseModel):
    """The agent's final answer, as structured fields; rendered to Markdown below.

    Making the answer a typed tool call means the model never has to write
    free text: every turn is a tool call, which keeps a small CPU model on
    track and makes evals (Phase 3) check fields instead of prose.
    """

    symptoms: str = Field(description="What the alert said and what you observed, two sentences.")
    evidence: list[str] = Field(
        description="At most three short quotes from tool outputs, one per item."
    )
    root_cause: str = Field(description="The cause and the git file that holds it, one sentence.")
    proposed_change: str = Field(
        description="The change you made, one line: file, old value -> new value."
    )
    confidence: str = Field(description="high, medium or low, then one short reason.")
    not_verified: str = Field(default="", description="What you could not check, one sentence.")
    pull_request_url: str = Field(default="", description="URL of the pull request you opened.")

    def markdown(self) -> str:
        evidence = "\n".join(f"- {e}" for e in self.evidence) or "- (none)"
        return (
            f"## Symptoms\n{self.symptoms}\n\n"
            f"## Evidence\n{evidence}\n\n"
            f"## Root cause\n{self.root_cause}\n\n"
            f"## Proposed change\n{self.proposed_change.strip()}\n\n"
            f"## Confidence\n{self.confidence}\n\n"
            f"## Not verified\n{self.not_verified or 'nothing'}\n"
            + (f"\nPull request: {self.pull_request_url}\n" if self.pull_request_url else "")
        )


@dataclass
class AgentSpec:
    manifest: AgentManifest
    resolved: dict[str, dict[str, str]]
    prompt: str
    directory: Path


def load_agent(agent_dir: Path, capmap: CapabilityMap) -> AgentSpec:
    """Load and validate an agent directory. Raises ManifestViolation on any forbidden tool."""
    manifest = load_manifest(agent_dir / "manifest.yaml")
    resolved = validate_manifest(manifest, capmap)
    prompt = (agent_dir / "prompt.md").read_text(encoding="utf-8")
    log.info(
        "agent %s: mutation=%s, tools:\n%s", manifest.name, manifest.mutation, describe(resolved)
    )
    return AgentSpec(manifest, resolved, prompt, agent_dir)


def new_run_id() -> str:
    return f"run-{secrets.token_hex(4)}"


class Runner:
    def __init__(
        self,
        store: Store,
        spec: AgentSpec,
        mcp_doc: dict[str, Any],
        knowledge: Knowledge,
        model: Model | None = None,
        model_cfg: ModelConfig | None = None,
    ) -> None:
        self.store = store
        self.spec = spec
        self.mcp_doc = mcp_doc
        self.knowledge = knowledge
        self.model_cfg = model_cfg or ModelConfig.from_env()
        self._model = model
        self.repo = os.environ.get("GITHUB_REPO", "asaf-1/DevOps-Platform")

    @property
    def model(self) -> Model:
        if self._model is None:
            self._model = build_model(self.model_cfg)
        return self._model

    def instructions(self, alert: dict[str, Any]) -> str:
        m = self.spec.manifest
        labels = alert.get("labels", {})
        parts = [self.spec.prompt.strip()]
        namespaces = ", ".join(m.allowed_namespaces)
        parts.append(
            "## Scope and rules enforced by the runtime\n"
            f"- Allowed namespaces: {namespaces}. Every Kubernetes tool call must name one.\n"
            f"- GitOps repository: {self.repo}, base branch main. "
            "Desired state of the app: gitops/apps/<app>/.\n"
            "- You may only create branches named agent/incident-<fingerprint> "
            "and open pull requests from them.\n"
            f"- Budget: at most {m.max_steps} model steps and {m.token_budget} tokens. "
            "Be economical.\n"
            "- Tool calls that break a rule return a line starting with REFUSED; "
            "read it and adjust."
        )
        section = self.knowledge.prompt_section(alert_tags(labels), set(m.knowledge_tags))
        if section:
            parts.append(section)
        return "\n\n".join(parts)

    @staticmethod
    def user_prompt(alert: dict[str, Any], fingerprint: str) -> str:
        labels = alert.get("labels", {})
        annotations = alert.get("annotations", {})
        app = labels.get("deployment") or labels.get("container") or ""
        gitops_file = (
            f"GitOps file of this workload: gitops/apps/{app}/deployment.yaml "
            "(use this exact path)\n"
            if app
            else ""
        )
        return (
            f"An alert fired. Fingerprint: {fingerprint}\n"
            f"Alert: {labels.get('alertname', '?')} (severity {labels.get('severity', '?')})\n"
            f"Namespace: {labels.get('namespace', '?')}  Pod: {labels.get('pod', '?')}  "
            f"Container: {labels.get('container', '?')}\n"
            f"Summary: {annotations.get('summary', '')}\n"
            f"Description: {annotations.get('description', '')}\n"
            f"Labels: {json.dumps(labels, sort_keys=True)}\n"
            f"{gitops_file}\n"
            "Diagnose it and propose the fix as a pull request, then answer with the report "
            "and the pull request URL."
        )

    async def run(
        self, run_id: str, alert: dict[str, Any], fixture: Any | None = None
    ) -> dict[str, Any]:
        """Run the agent for one alert. A fixture replaces the MCP tools (evals, dry runs).

        Each run is its own trace (the webhook request that started it is a
        link, not a parent), so the run's trace id opens it in Grafana.
        """
        m = self.spec.manifest
        if fixture is not None and getattr(fixture, "overrides", None):
            m = m.model_copy(update=dict(fixture.overrides))
        tracer = trace.get_tracer("agent-runtime")
        parent = trace.get_current_span().get_span_context()
        links = [trace.Link(parent)] if parent.is_valid else []
        with tracer.start_as_current_span(
            f"agent run {m.name}", context=Context(), links=links
        ) as span:
            labels = alert.get("labels", {})
            span.set_attribute("run.id", run_id)
            span.set_attribute("alert.name", str(labels.get("alertname", "")))
            span.set_attribute("alert.namespace", str(labels.get("namespace", "")))
            span.set_attribute("model", f"{self.model_cfg.provider}:{self.model_cfg.name}")
            ctx = span.get_span_context()
            if ctx.is_valid:
                self.store.set_trace(run_id, format(ctx.trace_id, "032x"))
            return await self._run(run_id, alert, m, fixture)

    async def _run(
        self, run_id: str, alert: dict[str, Any], m: AgentManifest, fixture: Any | None
    ) -> dict[str, Any]:
        fingerprint = str(alert.get("fingerprint") or run_id)
        guard = ToolGuard(
            allowed_tools=set(m.allowed_tools),
            allowed_namespaces=set(m.allowed_namespaces),
            agent=m.name,
            run_id=run_id,
            store=self.store,
        )
        toolsets = build_toolsets(
            self.mcp_doc, m, guard, make_local_toolset(self.repo), fixture=fixture
        )
        self.store.audit(
            "agent.run.started",
            actor=m.name,
            details={
                "run_id": run_id,
                "fingerprint": fingerprint,
                "alert": alert.get("labels", {}),
                "model": f"{self.model_cfg.provider}:{self.model_cfg.name}",
            },
        )
        agent: Agent[None, IncidentReport] = Agent(
            self.model,
            name=m.name,
            instructions=self.instructions(alert),
            toolsets=toolsets,
            output_type=IncidentReport,
            retries=2,
        )
        try:
            result = await agent.run(
                self.user_prompt(alert, fingerprint),
                usage_limits=UsageLimits(
                    request_limit=m.max_steps, total_tokens_limit=m.token_budget
                ),
            )
        except Exception as e:
            log.exception("run %s failed", run_id)
            self.store.audit(
                "agent.run.failed", actor=m.name, details={"run_id": run_id, "error": str(e)[:500]}
            )
            return self.store.finish_run(
                run_id,
                status="failed",
                error=str(e)[:2000],
                usage={"tool_calls": len(guard.records)},
            )
        output = result.output
        report = output.markdown() if isinstance(output, IncidentReport) else str(output)
        pr_url = _find_pr_url(report, guard.records)
        usage = result.usage  # a property in Pydantic AI 2.x; a method in 1.x
        if callable(usage):
            usage = usage()
        usage_dict = {
            "requests": getattr(usage, "requests", None),
            "input_tokens": getattr(usage, "input_tokens", None),
            "output_tokens": getattr(usage, "output_tokens", None),
            "total_tokens": getattr(usage, "total_tokens", None),
            "tool_calls": len(guard.records),
            "refused_calls": sum(1 for r in guard.records if r.refused),
        }
        self.store.audit(
            "agent.run.finished",
            actor=m.name,
            details={"run_id": run_id, "pr_url": pr_url, "usage": usage_dict},
        )
        return self.store.finish_run(
            run_id, status="done", report=report, pr_url=pr_url, usage=usage_dict
        )


def _find_pr_url(report: str, records: list[Any]) -> str | None:
    m = _PR_URL.search(report)
    if m:
        return m.group(0)
    for rec in reversed(records):
        if rec.tool.endswith("create_pull_request") and rec.ok:
            m = _PR_URL.search(rec.preview)
            if m:
                return m.group(0)
    return None


def default_paths() -> tuple[Path, Path, Path]:
    """(agents dir, runbooks dir, agent dir) from env or the repo layout."""
    agents_dir = Path(os.environ.get("AGENTS_DIR", Path(__file__).resolve().parents[1]))
    runbooks = Path(os.environ.get("RUNBOOKS_DIR", agents_dir.parent / "docs" / "runbooks"))
    agent_dir = agents_dir / os.environ.get("AGENT_NAME", "incident_triage")
    return agents_dir, runbooks, agent_dir


def build_runner(store: Store, model: Model | None = None) -> Runner:
    agents_dir, runbooks_dir, agent_dir = default_paths()
    capmap = CapabilityMap.load(
        agents_dir / "tools" / "capabilities.yaml", agents_dir / "tools" / "mcp.yaml"
    )
    spec = load_agent(agent_dir, capmap)
    mcp_doc = load_yaml(agents_dir / "tools" / "mcp.yaml")
    knowledge = Knowledge.load(runbooks_dir)
    return Runner(store, spec, mcp_doc, knowledge, model=model)
