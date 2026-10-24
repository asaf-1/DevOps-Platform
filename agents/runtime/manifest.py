"""Agent manifests and the capability map, validated before anything runs.

An agent declares what it may use. The capability map declares what each
tool can do (read, write, delete) and on which target (cluster, github,
observability, local). A propose-only agent may hold no tool that writes
or deletes on the cluster and no delete tool anywhere. Violations stop the
runtime at startup, loudly, naming the tool.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator

Capability = Literal["read", "write", "delete"]


class ManifestViolation(ValueError):
    """The manifest asks for something the mutation mode forbids."""


class ModelRef(BaseModel):
    provider: str = "${MODEL_PROVIDER}"
    name: str = "${MODEL_NAME}"


class ReportSpec(BaseModel):
    required_sections: list[str] = Field(default_factory=list)


class AgentManifest(BaseModel):
    name: str
    description: str = ""
    model: ModelRef = Field(default_factory=ModelRef)
    mutation: Literal["propose_only"] = "propose_only"
    allowed_namespaces: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    allowed_tools_file: str | None = None
    max_steps: int = Field(default=12, ge=1, le=100)
    token_budget: int = Field(default=24000, ge=1000)
    knowledge_tags: list[str] = Field(default_factory=list)
    report: ReportSpec = Field(default_factory=ReportSpec)

    @field_validator("allowed_tools")
    @classmethod
    def _qualified(cls, tools: list[str]) -> list[str]:
        bad = [t for t in tools if "." not in t]
        if bad:
            raise ValueError(f"tools must be '<server>.<tool>': {bad}")
        return tools


def _expand_env(value: str) -> str:
    return re.sub(r"\$\{([A-Z0-9_]+)\}", lambda m: os.environ.get(m.group(1), ""), value)


def load_manifest(path: Path) -> AgentManifest:
    """Read manifest.yaml; pull allowed_tools from allowed_tools_file if set."""
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    model = data.get("model") or {}
    data["model"] = {k: _expand_env(str(v)) for k, v in model.items()}
    manifest = AgentManifest(**data)
    if manifest.allowed_tools_file:
        tools_doc = (
            yaml.safe_load((path.parent / manifest.allowed_tools_file).read_text(encoding="utf-8"))
            or {}
        )
        manifest = manifest.model_copy(
            update={
                "allowed_tools": list(manifest.allowed_tools)
                + list(tools_doc.get("allowed_tools", []))
            }
        )
    return manifest


class CapabilityRule(BaseModel):
    match: str
    capability: Capability

    def regex(self) -> re.Pattern[str]:
        return re.compile(f"^(?:{self.match})$")


class CapabilityMap:
    """First matching rule wins; a tool with no rule is an error, not a default."""

    def __init__(self, rules: list[CapabilityRule], targets: dict[str, str]) -> None:
        self.rules = rules
        self._compiled = [(r.regex(), r.capability) for r in rules]
        self.targets = targets  # server name -> target (cluster, github, observability, local)

    @classmethod
    def load(cls, capabilities_path: Path, mcp_path: Path) -> CapabilityMap:
        cap_doc = yaml.safe_load(capabilities_path.read_text(encoding="utf-8")) or {}
        mcp_doc = yaml.safe_load(mcp_path.read_text(encoding="utf-8")) or {}
        rules = [CapabilityRule(**r) for r in cap_doc.get("rules", [])]
        targets = {
            name: str(spec.get("target", "cluster"))
            for name, spec in (mcp_doc.get("servers") or {}).items()
        }
        targets["local"] = "local"
        return cls(rules, targets)

    def capability(self, qualified_tool: str) -> Capability:
        for pattern, cap in self._compiled:
            if pattern.match(qualified_tool):
                return cap
        raise ManifestViolation(
            f"no capability rule for tool {qualified_tool!r}; add one to capabilities.yaml"
        )

    def target(self, qualified_tool: str) -> str:
        server = qualified_tool.split(".", 1)[0]
        try:
            return self.targets[server]
        except KeyError:
            raise ManifestViolation(
                f"tool {qualified_tool!r} names unknown server {server!r}"
            ) from None


def validate_manifest(manifest: AgentManifest, capmap: CapabilityMap) -> dict[str, dict[str, str]]:
    """Return {tool: {capability, target}} for allowed tools, or raise ManifestViolation.

    propose_only: no write or delete on the cluster, no delete anywhere.
    """
    resolved: dict[str, dict[str, str]] = {}
    violations: list[str] = []
    for tool in manifest.allowed_tools:
        cap = capmap.capability(tool)
        target = capmap.target(tool)
        resolved[tool] = {"capability": cap, "target": target}
        if manifest.mutation == "propose_only":
            if target == "cluster" and cap in ("write", "delete"):
                violations.append(f"{tool} is {cap} on the cluster")
            elif cap == "delete":
                violations.append(f"{tool} is delete on {target}")
    if violations:
        raise ManifestViolation(
            f"agent {manifest.name!r} is propose_only but its manifest grants: "
            + "; ".join(violations)
        )
    if not manifest.allowed_namespaces:
        raise ManifestViolation(f"agent {manifest.name!r} has no allowed_namespaces")
    return resolved


def describe(resolved: dict[str, dict[str, str]]) -> str:
    return "\n".join(
        f"  {t:<36} {v['capability']:<6} {v['target']}" for t, v in sorted(resolved.items())
    )


def load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
