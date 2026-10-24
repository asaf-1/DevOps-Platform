# Real AWS. Only used when REAL_AWS=1 (Phase 4). Credentials come from the
# environment: GitHub Actions OIDC in CI, a local profile on a laptop.
# Never from this file.
provider "aws" {
  region = var.region

  default_tags {
    tags = {
      environment = "dev"
    }
  }
}
