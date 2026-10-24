"""FastAPI service: catalog, requests, audit.

POST /requests validates the inputs, stores the request, renders its one
Terraform file, pushes a branch and opens the pull request. From there CI,
a human reviewer and the apply worker move it along; the API only records.
"""

from __future__ import annotations

import json
import secrets
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from pydantic import BaseModel

from . import __version__
from .catalog import Catalog, CatalogError
from .github import GitHub, GitHubClient, GitHubError
from .models import AuditEvent, CatalogType, RequestCreate, RequestState, ResourceRequest
from .render import Renderer, request_file_path
from .settings import Settings
from .storage import Store, make_engine

PR_LABEL = "platform-request"


class Services:
    """Everything the endpoints need, built once at startup or injected by tests."""

    def __init__(
        self,
        settings: Settings,
        catalog: Catalog,
        renderer: Renderer,
        store: Store,
        github: GitHub | None,
    ) -> None:
        self.settings = settings
        self.catalog = catalog
        self.renderer = renderer
        self.store = store
        self.github = github


def build_services(settings: Settings | None = None, github: GitHub | None = None) -> Services:
    settings = settings or Settings.from_env()
    catalog = Catalog(settings.catalog_dir)
    renderer = Renderer(catalog)
    store = Store(make_engine(settings.database_url))
    if github is None and settings.github_token:
        github = GitHubClient(
            settings.github_repo,
            settings.github_token,
            base_branch=settings.github_base_branch,
            api_url=settings.github_api_url,
        )
    return Services(settings, catalog, renderer, store, github)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not hasattr(app.state, "services"):
        app.state.services = build_services()
    yield


app = FastAPI(title="Platform API", version=__version__, lifespan=lifespan)


def services(request: Request) -> Services:
    return request.app.state.services


# catalog


class CatalogEntry(BaseModel):
    type: str
    display_name: str
    description: str
    provider: str
    approval_required: bool
    environments: list[str]
    inputs: dict[str, Any]


def _entry(ctype: CatalogType) -> CatalogEntry:
    return CatalogEntry(
        type=ctype.type,
        display_name=ctype.display_name,
        description=ctype.description,
        provider=ctype.provider,
        approval_required=ctype.approval_required,
        environments=ctype.environments,
        inputs=ctype.input_schema.get("properties", {}),
    )


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.get("/catalog", response_model=list[CatalogEntry])
def list_catalog(svc: Services = Depends(services)) -> list[CatalogEntry]:
    return [_entry(t) for t in svc.catalog.types.values()]


@app.get("/catalog/{type_name}", response_model=CatalogType)
def get_catalog_type(type_name: str, svc: Services = Depends(services)) -> CatalogType:
    try:
        return svc.catalog.get(type_name)
    except CatalogError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


# requests


def new_request_id() -> str:
    return f"r-{secrets.token_hex(3)}"


def pr_title(req: ResourceRequest) -> str:
    return f"[{req.type}] {req.inputs.get('name', req.id)} for team {req.inputs.get('team', '?')}"


def pr_body(req: ResourceRequest, ctype: CatalogType) -> str:
    inputs = "\n".join(f"- `{k}`: `{v}`" for k, v in sorted(req.inputs.items()))
    machine = json.dumps(
        {
            "request_id": req.id,
            "type": req.type,
            "environment": req.environment,
            "requested_by": req.requested_by,
            "inputs": req.inputs,
        },
        indent=2,
        sort_keys=True,
    )
    return (
        f"## {ctype.display_name} request `{req.id}`\n\n"
        f"Requested by **{req.requested_by}** for environment **{req.environment}**.\n\n"
        f"{ctype.description}\n\n"
        f"### Inputs\n{inputs}\n\n"
        f"### What happens next\n"
        f"1. CI runs `terraform plan`, the `{ctype.policy_set}` policies, Checkov and an "
        f"Infracost estimate and comments here.\n"
        f"2. A reviewer approves and merges.\n"
        f"3. The apply worker in the cluster applies it and records the audit trail.\n\n"
        f"Owner team: `{ctype.owner_team}`. Module: `{ctype.module}`.\n\n"
        f"<!-- platform-request\n{machine}\n-->\n"
    )


@app.post("/requests", response_model=ResourceRequest, status_code=201)
def create_request(payload: RequestCreate, svc: Services = Depends(services)) -> ResourceRequest:
    try:
        ctype = svc.catalog.get(payload.type)
        inputs = svc.catalog.validate_inputs(payload.type, payload.inputs)
    except CatalogError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    if payload.environment not in ctype.environments:
        raise HTTPException(
            status_code=422,
            detail=f"{payload.type} is not offered in environment {payload.environment!r}",
        )

    request_id = new_request_id()
    while svc.store.get_request(request_id) is not None:
        request_id = new_request_id()
    req = svc.store.create_request(
        request_id, payload.type, payload.environment, inputs, payload.requested_by
    )

    if svc.github is None:
        return svc.store.transition(
            req.id,
            RequestState.FAILED,
            actor="platform-api",
            details={"reason": "GitHub is not configured (PLATFORM_GITHUB_TOKEN missing)"},
            error="GitHub is not configured",
        )

    tf_text = svc.renderer.render(payload.type, req.id, inputs)
    rel_path = request_file_path(svc.settings.repo_root, req.environment, req.id).relative_to(
        svc.settings.repo_root
    )
    branch = f"request/{req.id}"
    try:
        svc.github.create_branch_with_file(
            branch,
            rel_path.as_posix(),
            tf_text,
            f"{req.type} {inputs.get('name', req.id)}: request {req.id}",
        )
        pr = svc.github.open_pull_request(pr_title(req), pr_body(req, ctype), branch, [PR_LABEL])
    except GitHubError as e:
        return svc.store.transition(
            req.id,
            RequestState.FAILED,
            actor="platform-api",
            details={"reason": str(e)},
            error=str(e),
            branch=branch,
        )
    return svc.store.transition(
        req.id,
        RequestState.PR_OPENED,
        actor="platform-api",
        details={"pr_number": pr.number, "pr_url": pr.html_url, "path": rel_path.as_posix()},
        branch=branch,
        pr_number=pr.number,
        pr_url=pr.html_url,
    )


@app.get("/requests", response_model=list[ResourceRequest])
def list_requests(
    state: RequestState | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    svc: Services = Depends(services),
) -> list[ResourceRequest]:
    return svc.store.list_requests(state=state, limit=limit)


@app.get("/requests/{request_id}", response_model=ResourceRequest)
def get_request(request_id: str, svc: Services = Depends(services)) -> ResourceRequest:
    req = svc.store.get_request(request_id)
    if req is None:
        raise HTTPException(status_code=404, detail=f"no request {request_id}")
    return req


# audit


@app.get("/audit", response_model=list[AuditEvent])
def list_audit(
    request: str | None = Query(default=None, description="Filter by request id"),
    limit: int = Query(default=500, ge=1, le=5000),
    svc: Services = Depends(services),
) -> list[AuditEvent]:
    return svc.store.list_events(request_id=request, limit=limit)
