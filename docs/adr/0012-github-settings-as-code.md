# 0012. The repository's GitHub settings as Terraform, applied by a person

Date: 2026-10-25. Status: accepted.

## Context

Phase 1 created the `production` environment, its required reviewer and
the `platform-request` label by hand through the GitHub API, and
auto-merge was switched on by a click. Asaf asked (2026-10-24) that these
be code, "because it's infrastructure as code". Everything else in this
repository is applied by the apply worker inside the cluster with the
`pg` state backend.

## Decision

- **A Terraform root, `infra/terraform/github/`**, with the
  `integrations/github` provider: the repository's settings (visibility,
  features, auto-merge, delete-branch-on-merge, topics), the `production`
  environment with its reviewer, protection of `main` against deletion and
  force-push, and the request label. Existing objects are adopted with
  `import` blocks on the first apply.
- **Secrets are checked, not created.** A `check` block warns on every plan
  when an optional secret (`ANTHROPIC_API_KEY`, `INFRACOST_API_KEY`) is
  missing. Creating secrets in Terraform would put their values in state.
- **Applied by a person from the devcontainer, not by the worker.** The
  changes need a token with Administration rights on the repository. The
  worker's token has Contents and Pull requests only, and that is the right
  shape for something that runs unattended next to an AI agent. So
  `make github-settings` plans, `APPLY=1 make github-settings` applies,
  with `GITHUB_ADMIN_TOKEN` from `.env` exported only for that process.
  State still lives in the platform's Postgres (schema `terraform_github`)
  through a port-forward, so plans see the real state.
- **Review is the pull request.** A change to the folder is reviewed like
  code, `make lint` validates and formats it, and the person who merges it
  runs the apply. No required-review rule on `main`: the platform API, the
  build bot and the break/fix scripts push to `main` by design.

## Alternatives considered

- **Apply from GitHub Actions with the same approval gate as requests.**
  Needs the admin token as a repository secret, readable by any workflow in
  the repository, and the state backend reachable from the runner, which the
  in-cluster Postgres is not. Rejected for now; it is the natural step once
  the state moves to a cloud backend (Phase 4, real AWS option).
- **Branch protection that requires pull requests on `main`.** Would block
  the platform's own pushes (request PR auto-merge is fine, but the build
  bot's tag bumps and `make break` are direct pushes). Rejected until those
  become pull requests too.

## Consequences

- The clicks of Phase 1 are reproducible: a new fork of this repository
  gets its environment, reviewer, rules and label from one apply.
- A second token with wider rights exists on the owner's machine only.
