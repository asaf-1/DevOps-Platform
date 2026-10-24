# 0001. Run on kind and LocalStack by default, real AWS only as a mode

- Status: accepted
- Date: 2026-10-24
- Deciders: Asaf

## Context

The platform must show the same things an EKS-based internal developer
platform shows: a cluster managed by GitOps, cloud resources created by
Terraform through a reviewed path, policies, cost estimates and an audit
trail. EKS costs about 0.10 USD per cluster-hour plus nodes, roughly 75 USD a
month if left on, and every eval run in CI would need cloud credentials.
This is a portfolio project built on one laptop (PLAN.md section 8.1) with a
budget of a few dollars for the demo recording.

## Decision

The default target is a local kind cluster (`gitops/clusters/local/kind.yaml`)
and LocalStack Community running inside it for S3, DynamoDB, IAM, STS, SQS
and CloudWatch. Terraform and the AWS CLI point at LocalStack through an
explicit endpoint and a dummy profile. Real AWS is a mode, not a default:
`REAL_AWS=1` plus a GitHub Actions OIDC role, used in Phase 4 for a few
hours to record the demo, and only when Asaf asks for it in that session.

## Consequences

- Everything runs offline and costs nothing; CI on a public repo can run
  the full plan, policy and apply path against LocalStack.
- LocalStack Community does not emulate everything. The catalog stays on
  services it covers well (S3, DynamoDB, IAM, SQS). Anything beyond that
  is a Phase 4 real-AWS demonstration, not a local one.
- The same Terraform modules run against both backends; the environment
  folder (`infra/terraform/envs/local` vs `dev`) selects provider endpoints
  and state backend. Any drift between the two is a bug to fix in the
  module, not a reason to fork it.
- There is no cloud identity inside the cluster. The apply worker uses
  dummy credentials locally; on real AWS it would need IRSA or Pod Identity,
  which the ADR for Phase 4 must cover.
- The laptop has 24 GB of RAM and no GPU, so the cluster is sized small and
  the local model is small (PLAN.md section 8.6).

## Alternatives considered

- EKS always on: the most faithful, but 75 USD a month and credentials in
  CI for every run. Rejected on cost; kept for the demo video only.
- k3d or minikube: equivalent for this purpose. kind was already installed
  and its port mappings make the ingress and LocalStack reachable on
  localhost without extra tooling.
- Moto instead of LocalStack: lighter, but Terraform's AWS provider and the
  CLI work against LocalStack with no code changes, which matters more here.
