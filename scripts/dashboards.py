"""Generate the two Grafana dashboards as ConfigMaps (dashboards as code).

    python scripts/dashboards.py          # rewrites gitops/clusters/local/dashboards/*.yaml

The YAML is the artifact in git; edit a panel here and regenerate. Every
query aggregates over pods (sum or max), because each pod restart starts a
new series and a stat panel would otherwise show one number per restart.
"""

import json
import os
from pathlib import Path

ROOT = Path(os.environ.get("REPO_ROOT", Path(__file__).resolve().parents[1]))
OUT = ROOT / "gitops" / "clusters" / "local" / "dashboards"
PROM = {"type": "prometheus", "uid": "prometheus"}


def panel(pid, ptype, title, exprs, x, y, w, h, unit=None, legend=None, extra=None):
    targets = []
    for i, e in enumerate(exprs):
        t = {"refId": chr(65 + i), "datasource": PROM, "expr": e}
        if legend:
            t["legendFormat"] = legend[i] if isinstance(legend, list) else legend
        targets.append(t)
    p = {
        "id": pid,
        "type": ptype,
        "title": title,
        "datasource": PROM,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "targets": targets,
        "fieldConfig": {"defaults": {}, "overrides": []},
        "options": {},
    }
    if unit:
        p["fieldConfig"]["defaults"]["unit"] = unit
    if ptype == "stat":
        p["options"] = {
            "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
            "colorMode": "value",
            "graphMode": "none",
            "textMode": "auto",
        }
    if ptype == "bargauge":
        p["options"] = {
            "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
            "orientation": "horizontal",
            "displayMode": "gradient",
        }
    if ptype == "timeseries":
        p["options"] = {"legend": {"displayMode": "list", "placement": "bottom"}}
    if extra:
        p.update(extra)
    return p


def dashboard(uid, title, tags, panels, description):
    return {
        "uid": uid,
        "title": title,
        "description": description,
        "tags": tags,
        "editable": True,
        "schemaVersion": 39,
        "version": 1,
        "time": {"from": "now-7d", "to": "now"},
        "refresh": "1m",
        "templating": {"list": []},
        "panels": panels,
    }


dx = dashboard(
    "platform-dx",
    "Platform DX",
    ["platform", "dx"],
    [
        panel(1, "stat", "Requests (all time)", ["sum(platform_requests)"], 0, 0, 4, 4),
        panel(2, "stat", "Created, last 7 days", ["max(platform_requests_created_7d)"], 4, 0, 4, 4),
        panel(
            3, "stat", "Request to deployed, p50",
            ['max(platform_request_time_to_deployed_seconds{quantile="0.5"})'], 8, 0, 4, 4, unit="s",
        ),
        panel(
            4, "stat", "Request to deployed, p95",
            ['max(platform_request_time_to_deployed_seconds{quantile="0.95"})'], 12, 0, 4, 4, unit="s",
        ),
        panel(
            5, "stat", "Approval wait, p50",
            ['max(platform_approval_wait_seconds{quantile="0.5"})'], 16, 0, 4, 4, unit="s",
        ),
        panel(
            6, "stat", "Requests that failed (any reason)",
            ['max(platform_requests{state="failed"}) / clamp_min(sum(max by (state) (platform_requests)), 1)'],
            20, 0, 4, 4, unit="percentunit",
        ),
        panel(
            7, "bargauge", "Requests by state", ["max by (state) (platform_requests)"], 0, 4, 12, 8,
            legend="{{state}}",
        ),
        panel(
            8, "timeseries", "Audit events by outcome",
            ['max by (outcome) (sum by (outcome, pod) (platform_audit_events))'], 12, 4, 12, 8, legend="{{outcome}}",
        ),
        panel(
            9, "timeseries", "Requests per state over time", ["max by (state) (platform_requests)"], 0, 12, 24, 8,
            legend="{{state}}",
        ),
    ],
    "Developer experience of the self-service path: throughput, time to production, approval wait, policy outcomes. Numbers come from the audit table through the platform API's /metrics.",
)

agents = dashboard(
    "platform-agents",
    "Agents",
    ["platform", "agents"],
    [
        panel(1, "stat", "Runs (all time)", ["sum(max by (status) (agent_runs))"], 0, 0, 4, 4),
        panel(
            2, "stat", "Success rate",
            ['max(agent_runs{status="done"}) / clamp_min(sum(max by (status) (agent_runs{status=~"done|failed"})), 1)'],
            4, 0, 4, 4, unit="percentunit",
        ),
        panel(3, "stat", "Mean tool calls per run", ["max(agent_run_steps_mean)"], 8, 0, 4, 4),
        panel(4, "stat", "Mean tokens per run", ["max(agent_run_tokens_mean)"], 12, 0, 4, 4),
        panel(
            5, "stat", "Alert to report, p50",
            ['max(agent_run_duration_seconds{quantile="0.5"})'], 16, 0, 4, 4, unit="s",
        ),
        panel(
            6, "stat", "Eval score of deployed prompt", ["max(agent_eval_score)"], 20, 0, 4, 4,
            unit="percentunit",
        ),
        panel(7, "bargauge", "Runs by status", ["max by (status) (agent_runs)"], 0, 4, 8, 8, legend="{{status}}"),
        panel(
            8, "bargauge", "Tool calls by tool and outcome", ["max by (tool, outcome) (agent_tool_calls)"], 8, 4, 16, 8,
            legend="{{tool}} {{outcome}}",
        ),
        panel(
            9, "timeseries", "Refused and failed tool calls",
            ['max by (outcome) (sum by (outcome, pod) (agent_tool_calls{outcome=~"refused|error"}))'], 0, 12, 12, 8,
            legend="{{outcome}}",
        ),
        panel(
            10, "stat", "Runs closed by a resolved alert", ["max(agent_runs_closed)"], 12, 12, 6, 8
        ),
        panel(
            11, "stat", "Deployed prompt version", ["max by (version) (agent_prompt_info)"], 18, 12, 6, 8,
            legend="{{version}}",
            extra={"options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "textMode": "name", "colorMode": "none", "graphMode": "none"}},
        ),
    ],
    "The agent platform: runs, success rate, cost in steps and tokens, time from alert to report, tool calls and refusals, the deployed prompt version. From the agent runtime's /metrics.",
)

OUT.mkdir(parents=True, exist_ok=True)
for name, dash in (("platform-dx", dx), ("agents", agents)):
    body = json.dumps(dash, indent=2)
    indented = "\n".join("    " + line for line in body.splitlines())
    text = (
        f"# Grafana dashboard \"{dash['title']}\" as code. Generated once from a script\n"
        f"# (scripts/dashboards.py); edit the panel there and regenerate.\n"
        "# The Grafana sidecar loads every ConfigMap with label grafana_dashboard=1.\n"
        "apiVersion: v1\nkind: ConfigMap\nmetadata:\n"
        f"  name: dashboard-{name}\n  namespace: observability\n  labels:\n"
        "    grafana_dashboard: \"1\"\n    app.kubernetes.io/part-of: platform\n"
        f"data:\n  {name}.json: |\n{indented}\n"
    )
    (OUT / f"{name}.yaml").write_text(text, encoding="utf-8", newline="\n")
    print("wrote", OUT / f"{name}.yaml", len(body), "bytes of JSON")

app = """# Dashboards as code: plain ConfigMaps under gitops/clusters/local/dashboards,
# loaded by the Grafana sidecar (label grafana_dashboard=1).
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: dashboards
  namespace: argocd
  annotations:
    argocd.argoproj.io/sync-wave: "2"
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: platform
  source:
    repoURL: https://github.com/asaf-1/DevOps-Platform.git
    targetRevision: main
    path: gitops/clusters/local/dashboards
  destination:
    server: https://kubernetes.default.svc
    namespace: observability
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    retry:
      limit: 5
      backoff:
        duration: 10s
        factor: 2
        maxDuration: 3m
"""
(ROOT / "gitops" / "argocd" / "apps" / "dashboards.yaml").write_text(app, encoding="utf-8", newline="\n")
print("wrote gitops/argocd/apps/dashboards.yaml")
