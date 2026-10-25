# The repository, its production environment and the request label were
# created by hand (through the API) in Phase 1. The first apply adopts them
# into state instead of recreating them; afterwards these blocks are no-ops.
import {
  to = github_repository.platform
  id = "DevOps-Platform"
}

import {
  to = github_repository_environment.production
  id = "DevOps-Platform:production"
}

import {
  to = github_issue_label.platform_request
  id = "DevOps-Platform:platform-request"
}

import {
  to = github_repository_environment_deployment_policy.production_main
  id = "DevOps-Platform:production:64229378"
}
