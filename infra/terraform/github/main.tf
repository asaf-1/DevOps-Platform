# The repository's own settings as code (PLAN 7.4, first item; ADR 0012).
# What used to be clicks and API calls in Phase 1: the production environment
# with its required reviewer, the branch rules on main, the label the
# platform puts on request pull requests, and the repository's merge
# behaviour. The repository, the environment and the label already exist;
# imports.tf adopts them on the first apply.

data "github_user" "reviewer" {
  username = var.reviewer
}

resource "github_repository" "platform" {
  name        = var.repository
  description = "Internal developer platform: self-service cloud and Kubernetes resources on Terraform, plus an incident agent platform with guardrails, evals, traces and audit. Everything runs locally on kind, LocalStack and Ollama."
  visibility  = "public"
  topics      = var.topics

  has_issues      = true
  has_projects    = false
  has_wiki        = false
  has_discussions = false

  # The platform's worker merges request pull requests itself when CI is
  # green; GitHub's own auto-merge button is not used. Merged request/* and
  # agent/* branches are deleted so they do not pile up.
  allow_auto_merge       = false
  delete_branch_on_merge = true
  allow_update_branch    = true

  lifecycle {
    prevent_destroy = true
    # Managed elsewhere or by GitHub: pages, templates, archive state.
    ignore_changes = [pages, template, archived, archive_on_destroy]
  }
}

# One click stands between "approved pull request" and "applied": the
# production environment's required reviewer (iac-approve.yml waits on it).
resource "github_repository_environment" "production" {
  repository  = github_repository.platform.name
  environment = "production"

  reviewers {
    users = [data.github_user.reviewer.id]
  }

  # Only main may deploy to production (the policy below); set by hand in
  # Phase 1 and kept.
  deployment_branch_policy {
    protected_branches     = false
    custom_branch_policies = true
  }
}

resource "github_repository_environment_deployment_policy" "production_main" {
  repository     = github_repository.platform.name
  environment    = github_repository_environment.production.environment
  branch_pattern = "main"
}

# main cannot be deleted or force-pushed. No required reviews: the platform
# API, the build bot and the break/fix scripts push to main directly;
# requests and agent proposals arrive as pull requests by construction.
resource "github_branch_protection" "main" {
  repository_id = github_repository.platform.node_id
  pattern       = "main"

  allows_deletions    = false
  allows_force_pushes = false
}

resource "github_repository_vulnerability_alerts" "platform" {
  repository = github_repository.platform.name
}

# The label the platform API puts on every request pull request
# (PR_LABEL in platform/api/platform_api/main.py).
resource "github_issue_label" "platform_request" {
  repository  = github_repository.platform.name
  name        = "platform-request"
  color       = "0E8A16"
  description = "Opened by the platform API for a resource request"
}

# Secrets are never created here (their values would land in state); their
# existence is checked. A missing optional secret is a warning on every
# plan, which is exactly the reminder it should be.
data "github_actions_secrets" "repo" {
  name = github_repository.platform.name
}

check "optional_secrets_exist" {
  assert {
    condition = alltrue([
      for s in var.optional_secrets : contains(data.github_actions_secrets.repo.secrets[*].name, s)
    ])
    error_message = join(" ", [
      "Optional repository secrets missing:",
      join(", ", [for s in var.optional_secrets : s if !contains(data.github_actions_secrets.repo.secrets[*].name, s)]),
      "(ANTHROPIC_API_KEY enables the CI eval job on Claude, ADR 0009; INFRACOST_API_KEY enables cost estimates on request pull requests)."
    ])
  }
}
