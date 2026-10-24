# DevOps-Platform

An internal developer platform plus an infra AI agents platform, built to be
demonstrated end to end on one laptop. Developers request cloud and
Kubernetes resources from a catalog; a request becomes a Terraform pull
request with plan, policy and cost checks and an approval gate; an apply
worker in the cluster creates the resource and records an audit event. On
top of that, agents (local model or Claude, by config) triage incidents from
real alerts and open fix pull requests, with permission manifests, RBAC and
admission policies that make them propose-only, an eval suite in CI, and
OpenTelemetry traces for every run and tool call.

## Quickstart

Prerequisites: Docker Desktop running, VS Code with the Dev Containers
extension. Open this folder in VS Code and choose "Reopen in Container";
the container carries the whole Linux toolchain (Terraform, Pulumi,
kubectl, Helm, kind, Conftest, Checkov, Infracost, ArgoCD CLI, Trivy,
Promptfoo).

```bash
make up       # kind cluster + ArgoCD; ArgoCD syncs everything else from git
make status   # applications and pod health
make down     # delete the cluster
```

`make up` prints the ArgoCD and Grafana URLs and passwords when done.

## Where things are

- [PLAN.md](PLAN.md): what this proves, the architecture, the phased task
  lists and the current status. Start there.
- [docs/adr/](docs/adr/): architecture decision records for every
  non-obvious choice.
- `gitops/`: ArgoCD project, app of apps, per-component Helm values.
- `scripts/` and the `Makefile`: the only commands you need.
