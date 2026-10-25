# Contributing

This is a one-person portfolio project, but it is built as if a team
worked on it: every change is a commit on `main` or a pull request, and
the same checks run for both.

## Before you push

```bash
make lint
```

runs, inside the devcontainer: Ruff and pytest for the API, the CLI and the
agent runtime; `terraform fmt -check` and `terraform validate` for every
Terraform root; Conftest unit tests for the plan policies; Checkov with the
repository's configuration; the Kyverno policy test suite; and a syntax
check of every shell script. Nothing is pushed while it is red.

## What CI runs

| Workflow | When | What |
|---|---|---|
| `iac-pr` | a pull request touching `infra/terraform/envs/**` | `terraform plan`, OPA/Conftest policies, Checkov, Trivy, Infracost (when a key exists); results as a PR comment |
| `iac-approve` | a request PR is merged | waits for the `production` environment's reviewer, then signals the in-cluster worker to apply |
| `build` | a push to `main` touching the services or the demo app | builds and pushes the images, bumps the image tags in git (`[skip ci]`) |
| `build-tenant` | the tenant app's pin changes | builds the tenant app from its pinned commit |
| `agents-eval` | a pull request or push touching `agents/**` or the runbooks | lint, manifest validation, guard rules, fixture schema, runner on a test model; the eval suite on Claude when `ANTHROPIC_API_KEY` exists |

## Where things go

- A new resource type: a folder under `platform/catalog/` (see its README)
  and a module under `infra/terraform/modules/`.
- A new agent: a folder under `agents/` with `manifest.yaml`, `tools.yaml`
  and `prompt.md`; capability rules in `agents/tools/capabilities.yaml`;
  runbooks in `docs/runbooks/` with tags; a recorded scenario in
  `agents/evals/fixtures/`.
- A non-obvious decision: an ADR in `docs/adr/` from the template.
- Anything the cluster should run: a commit under `gitops/`; ArgoCD
  applies it. Never `kubectl apply` by hand.

## Rules that are not negotiable

- Agents are propose-only. No tool with cluster write or delete capability,
  no direct push to `main`; the manifest check, RBAC and Kyverno each
  enforce it on their own.
- No secrets in git: `.env`, Terraform state, kubeconfigs and tokens stay
  out. Check the staged diff before every commit.
- Everything pinned and reviewable: chart versions, tool versions, one
  Terraform file per request, dashboards and policies as code.
