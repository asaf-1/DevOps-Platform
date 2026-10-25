output "repository_url" {
  value = github_repository.platform.html_url
}

output "production_reviewer" {
  description = "Who must approve deployments to production."
  value       = data.github_user.reviewer.login
}

output "main_branch_rules" {
  value = {
    pattern             = github_branch_protection.main.pattern
    allows_deletions    = github_branch_protection.main.allows_deletions
    allows_force_pushes = github_branch_protection.main.allows_force_pushes
  }
}

output "request_label" {
  value = github_issue_label.platform_request.name
}

output "secrets_present" {
  description = "Repository secrets that exist (names only)."
  value       = data.github_actions_secrets.repo.secrets[*].name
}
