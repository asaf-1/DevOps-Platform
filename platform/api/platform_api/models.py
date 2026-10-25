"""Pydantic models shared by the API, the CLI and the worker."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class RequestState(StrEnum):
    """Life of a request. Transitions are recorded as audit events."""

    REQUESTED = "requested"
    PR_OPENED = "pr-opened"
    PLANNED = "planned"
    APPROVED = "approved"
    APPLIED = "applied"
    DEPLOYED = "deployed"
    FAILED = "failed"


class CatalogType(BaseModel):
    """One folder under platform/catalog/<type>/."""

    model_config = ConfigDict(populate_by_name=True)

    type: str
    display_name: str
    description: str = ""
    provider: Literal["aws", "kubernetes"]
    module: str
    owner_team: str
    policy_set: str
    approval_required: bool = True
    # Merge the request PR automatically once CI is green. The approval gate
    # on the apply still applies when approval_required is true.
    auto_merge: bool = True
    environments: list[str] = Field(default_factory=lambda: ["local"])
    outputs: list[str] = Field(default_factory=list)
    input_schema: dict[str, Any] = Field(alias="schema")
    readme: str = ""


class RequestCreate(BaseModel):
    """What a developer sends to POST /requests."""

    type: str
    environment: str = "local"
    inputs: dict[str, Any]
    requested_by: str = Field(min_length=1, max_length=100)


class ResourceRequest(BaseModel):
    """A request and everything that happened to it."""

    id: str
    type: str
    environment: str
    inputs: dict[str, Any]
    requested_by: str
    state: RequestState
    created_at: datetime
    updated_at: datetime
    branch: str | None = None
    pr_number: int | None = None
    pr_url: str | None = None
    outputs: dict[str, Any] | None = None
    error: str | None = None


class AuditEvent(BaseModel):
    """One row of the audit trail. Humans, agents and the platform itself all write here."""

    id: int
    request_id: str | None
    event: str
    actor: str
    actor_type: Literal["human", "agent", "system"]
    at: datetime
    details: dict[str, Any] = Field(default_factory=dict)
    target: str | None = None  # what was acted on: "<type>/<name>", a tool, a PR
    run_id: str | None = None  # agent run, when an agent acted
    input_hash: str | None = None  # sha256 of the request inputs
    outcome: str | None = None  # ok, failed, refused, error
    approval_ref: str | None = None  # the approval this rests on (merge commit, approver)
    trace_id: str | None = None  # OpenTelemetry trace of the run
