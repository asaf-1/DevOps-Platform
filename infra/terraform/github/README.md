# The repository's GitHub settings as code

What Phase 1 created by hand through the API is Terraform here: the
`production` environment and its required reviewer, the rules on `main`,
the `platform-request` label, and the repository's merge behaviour
(auto-merge on, branches deleted after merge). Secrets are only checked for
existence, never created (their values would land in state).

```
make github-settings            # plan: what would change on GitHub
APPLY=1 make github-settings    # apply, after reading the plan
```

Needs `GITHUB_ADMIN_TOKEN` in `.env`: a fine-grained token scoped to this
repository with Administration (read and write), Environments (read and
write), Issues (read and write), Secrets (read) and Metadata (read). The
token stays with the person running the apply; the cluster never holds it
(ADR 0012). State lives in the platform's Postgres (schema
`terraform_github`) through a port-forward the script opens.

A change to these settings is a pull request on this folder, reviewed like
any other code; `make lint` validates it, and the apply is the reviewer's
own command after merge.
