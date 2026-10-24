# 0004. Approve in GitHub, execute in the cluster

- Status: accepted
- Date: 2026-10-24
- Deciders: Asaf

## Context

A request must be approved by a human before anything is created, and the
apply needs cloud credentials. The usual CI pattern puts both in GitHub
Actions: a job with `environment: production` waits for a reviewer and
then runs `terraform apply` with credentials from repo secrets. That puts
long-lived cloud credentials (or an OIDC role with broad rights) into CI
and ties the apply to a runner outside the platform.

## Decision

The approval happens in GitHub: the `iac-approve` workflow runs on every
merge to `main` that touches a request file, with `environment:
production` and a required reviewer. It does nothing but pass. The apply
happens in the cluster: the worker in the `platform-api` pod polls GitHub
for merged request PRs whose `iac-approve` run on the merge commit
succeeded, downloads the repo at that commit, runs Terraform with state in
Postgres against LocalStack (or real AWS in Phase 4 with IRSA), records
audit events for every transition, and commits the outputs back to the
GitOps folder for ArgoCD to roll out.

## Consequences

- Cloud credentials and Terraform state never leave the cluster; CI holds
  only a fine-grained GitHub token.
- Public repo is required: environment protection rules are free only
  there (PLAN.md section 4).
- The audit trail has a human actor for the approval (the merger's login
  on the `approved` event) and a system actor for the apply.
- The worker is a polling loop (30 s), not a webhook receiver, so the
  cluster needs no inbound access from GitHub. Latency is a minute, which
  the demo tolerates.
- `deployed` means "outputs committed to main"; ArgoCD's rollout of the
  demo app follows within its sync interval. The CLI timeline says so.
- If the worker pod restarts mid-apply, Terraform's state lock in Postgres
  and the idempotent state machine make the next pass safe.

## Alternatives considered

- Apply in GitHub Actions after approval: simpler, standard, but credentials
  in CI and an apply that the platform cannot observe or audit itself.
- A webhook from GitHub to the worker: faster, but needs a public endpoint
  on a laptop; polling is enough.
- Atlantis or Terraform Cloud run tasks: more moving parts than the demo
  needs, and the point is to show the mechanism, not to hide it.
