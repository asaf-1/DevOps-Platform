# One file per request lives next to this one: <request-id>.tf, rendered by
# the platform API from platform/catalog/<type>/request.tf.j2. Each holds a
# single module call and an output named after the request id. This file
# only declares the providers those modules use; keep it first.
terraform {
  required_providers {
    aws = {
      source = "hashicorp/aws"
    }
    kubernetes = {
      source = "hashicorp/kubernetes"
    }
  }
}
