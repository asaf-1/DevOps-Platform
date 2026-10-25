# The token comes from GITHUB_TOKEN in the environment: scripts/github-settings.sh
# exports GITHUB_ADMIN_TOKEN from .env under that name. A fine-grained token
# scoped to this repository with Administration (read and write), Environments
# (read and write), Issues (read and write), Secrets (read) and Metadata (read).
# It is held by the person running the apply, never by the cluster (ADR 0012).
provider "github" {
  owner = var.owner
}
