"""FastAPI front of the agent runtime.

POST /webhooks/alertmanager  Alertmanager calls this; one run per alert
                             fingerprint, deduplicated; resolved alerts
                             close the run with a note.
POST /runs                   manual trigger with an alert-shaped body
GET  /runs, GET /runs/{id}   steps, tool calls, report, PR URL
GET  /agent                  the validated manifest and resolved tools

Startup refuses to proceed if the manifest violates propose_only.
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from . import __version__
from .audit import Store
from .manifest import ManifestViolation
from .runner import Runner, build_runner, new_run_id
from .telemetry import setup_tracing

log = logging.getLogger("agent.server")
DEDUPE_MINUTES = int(os.environ.get("ALERT_DEDUPE_MINUTES", "30"))


class Services:
    def __init__(self, store: Store, runner: Runner) -> None:
        self.store = store
        self.runner = runner
        self.lock = asyncio.Lock()  # one run at a time: the local model is CPU-bound
        self.tasks: set[asyncio.Task[Any]] = set()

    def start(self, run_id: str, alert: dict[str, Any]) -> None:
        task = asyncio.create_task(self._execute(run_id, alert))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def _execute(self, run_id: str, alert: dict[str, Any]) -> None:
        async with self.lock:
            try:
                await self.runner.run(run_id, alert)
            except Exception as e:  # runner.run already records most failures
                log.exception("run %s crashed", run_id)
                try:
                    self.store.finish_run(run_id, status="failed", error=str(e)[:2000])
                except Exception:
                    pass


def build_services() -> Services:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    setup_tracing(os.environ.get("OTEL_SERVICE_NAME", "agent-runtime"))
    store = Store.from_env()
    try:
        runner = build_runner(store)
    except ManifestViolation as e:
        log.error("REFUSING TO START: %s", e)
        raise SystemExit(f"manifest violation: {e}") from e
    # Runs are in-process; anything still "running" was interrupted by a restart.
    for run in store.list_runs(limit=200):
        if run["status"] == "running":
            store.finish_run(run["id"], status="failed", error="interrupted by a runtime restart")
            log.warning("run %s marked failed: interrupted by restart", run["id"])
    return Services(store, runner)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not hasattr(app.state, "services"):
        app.state.services = build_services()
    yield


app = FastAPI(title="Agent runtime", version=__version__, lifespan=lifespan)


def services(request: Request) -> Services:
    return request.app.state.services


class Alert(BaseModel):
    status: str = "firing"
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)
    startsAt: str | None = None
    endsAt: str | None = None
    fingerprint: str | None = None
    generatorURL: str | None = None


class AlertmanagerPayload(BaseModel):
    status: str = "firing"
    receiver: str | None = None
    alerts: list[Alert] = Field(default_factory=list)
    groupLabels: dict[str, str] = Field(default_factory=dict)
    commonLabels: dict[str, str] = Field(default_factory=dict)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.get("/agent")
def agent_info(svc: Services = Depends(services)) -> dict[str, Any]:
    m = svc.runner.spec.manifest
    return {
        "name": m.name,
        "mutation": m.mutation,
        "model": f"{svc.runner.model_cfg.provider}:{svc.runner.model_cfg.name}",
        "allowed_namespaces": m.allowed_namespaces,
        "tools": svc.runner.spec.resolved,
        "max_steps": m.max_steps,
        "token_budget": m.token_budget,
    }


def _fingerprint(alert: Alert) -> str:
    if alert.fingerprint:
        return alert.fingerprint
    labels = alert.labels
    return (
        "-".join(
            str(labels.get(k, "")) for k in ("alertname", "namespace", "pod", "container")
        ).strip("-")
        or "manual"
    )


def _namespace_busy(store: Store, namespace: str | None) -> bool:
    """A triage for this namespace is in progress or finished recently.

    One broken pod raises several alerts (the app's own, plus Kubernetes'
    generic rollout and readiness alerts); they all describe one incident.
    """
    if not namespace:
        return False
    for run in store.list_runs(limit=20):
        labels = (run.get("alert") or {}).get("labels") or {}
        if labels.get("namespace") == namespace and _recent(run):
            return True
    return False


def _recent(run: dict[str, Any]) -> bool:
    """A run for this alert is in progress or finished recently; failed runs do not count."""
    if run["status"] == "running":
        return True
    if run["status"] == "failed":
        return False
    finished = run.get("finished_at")
    if not finished:
        return True
    when = datetime.fromisoformat(finished)
    if when.tzinfo is None:  # SQLite drops the offset; our timestamps are UTC
        when = when.replace(tzinfo=UTC)
    return when > datetime.now(UTC) - timedelta(minutes=DEDUPE_MINUTES)


@app.post("/webhooks/alertmanager")
async def alertmanager_webhook(
    payload: AlertmanagerPayload, svc: Services = Depends(services)
) -> dict[str, Any]:
    started: list[str] = []
    skipped: list[str] = []
    closed: list[str] = []
    for alert in payload.alerts:
        fp = _fingerprint(alert)
        latest = svc.store.latest_run_for(fp)
        if alert.status == "resolved":
            if latest and not latest.get("closure"):
                note = f"alert resolved at {alert.endsAt or datetime.now(UTC).isoformat()}"
                svc.store.close_run(latest["id"], note)
                svc.store.audit(
                    "agent.run.closed",
                    actor=svc.runner.spec.manifest.name,
                    details={"run_id": latest["id"], "note": note},
                )
                closed.append(latest["id"])
            continue
        if latest and _recent(latest):
            skipped.append(fp)
            continue
        if _namespace_busy(svc.store, alert.labels.get("namespace")):
            # One broken pod raises several alerts; one triage at a time per namespace.
            skipped.append(fp)
            continue
        run_id = new_run_id()
        svc.store.create_run(run_id, svc.runner.spec.manifest.name, fp, alert.model_dump())
        svc.start(run_id, alert.model_dump())
        started.append(run_id)
    return {"started": started, "skipped": skipped, "closed": closed}


@app.post("/runs", status_code=202)
async def manual_run(alert: Alert, svc: Services = Depends(services)) -> dict[str, Any]:
    fp = _fingerprint(alert)
    run_id = new_run_id()
    svc.store.create_run(run_id, svc.runner.spec.manifest.name, fp, alert.model_dump())
    svc.start(run_id, alert.model_dump())
    return {"id": run_id, "fingerprint": fp, "status": "running"}


@app.get("/runs")
def list_runs(limit: int = 50, svc: Services = Depends(services)) -> list[dict[str, Any]]:
    runs = svc.store.list_runs(limit=limit)
    for r in runs:  # keep the list light
        r.pop("steps", None)
        r["report"] = (r.get("report") or "")[:200]
    return runs


@app.get("/runs/{run_id}")
def get_run(run_id: str, svc: Services = Depends(services)) -> dict[str, Any]:
    run = svc.store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"no run {run_id}")
    return run
