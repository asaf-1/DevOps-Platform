# One file per request lives next to this one: <request-id>.tf. See
# infra/terraform/envs/README.md. Only AWS types are offered in dev.
terraform {
  required_providers {
    aws = {
      source = "hashicorp/aws"
    }
  }
}
