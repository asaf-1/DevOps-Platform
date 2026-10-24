# Local environment: AWS is LocalStack, Kubernetes is the kind cluster.
# Credentials are dummies; LocalStack accepts anything.

provider "aws" {
  region     = "us-east-1"
  access_key = "test"
  secret_key = "test"

  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
  skip_region_validation      = true
  s3_use_path_style           = true

  endpoints {
    s3         = var.localstack_endpoint
    dynamodb   = var.localstack_endpoint
    iam        = var.localstack_endpoint
    sts        = var.localstack_endpoint
    sqs        = var.localstack_endpoint
    cloudwatch = var.localstack_endpoint
  }

  default_tags {
    tags = {
      environment = "local"
    }
  }
}

# With no config_path the provider falls back to KUBE_CONFIG_PATH, then to
# in-cluster credentials (the apply worker's ServiceAccount).
provider "kubernetes" {
  config_path = var.kubeconfig_path
}
