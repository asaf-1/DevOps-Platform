# 0003. Terraform for the reviewed path, Pulumi for the programmatic path

- Status: accepted
- Date: 2026-10-24
- Deciders: Asaf

## Context

Developers request resources through a review. The job post names both
Terraform and Pulumi. Two tools for one job would double the modules,
policies and tests; one tool for everything would hide a real trade-off
that platform teams face: declarative files in pull requests versus
programs that create environments on demand.

## Decision

Terraform is the primary path. Every request becomes one Terraform file in
`infra/terraform/envs/<env>/requests/`, planned in CI, applied by the
in-cluster worker. Modules carry the safe defaults; OPA policies check the
plan. Pulumi (TypeScript, Automation API) is the programmatic path for
ephemeral preview environments, where a program that creates, tests and
destroys a stack beats a file in a pull request. Pulumi uses the local file
backend; HCP Terraform is not used for state. For real AWS in Phase 4,
HCP Terraform's free tier is the candidate remote state backend (Asaf has an
account); locally and in CI the state is the platform's Postgres, so a
clone needs no accounts.

## Consequences

- One module set to maintain. The catalog maps to Terraform modules only.
- Pulumi shows up where it is strongest and nowhere else; there is no
  "Pulumi flavour" of a request.
- Policy is written once, as Rego over Terraform plan JSON. Pulumi stacks
  get a smaller check (CrossGuard) if time allows.
- Terraform state in Postgres means the `pg` backend and a reachable
  database; CI plans use a throwaway local backend instead.
- Terraform is BSL-licensed; the use here is allowed. OpenTofu is a drop-in
  alternative if that ever changes.

## Alternatives considered

- Pulumi for everything: the Automation API could render and apply
  requests too, but reviewers read HCL diffs more easily than program
  diffs, and the job post's "Terraform" would be missing.
- Terraform for everything, including previews: possible with workspaces,
  but it hides the strength of a programmatic tool, which is the point of
  having Pulumi in the picture.
- CDK for Terraform: a third model; not named in the post; skipped.
