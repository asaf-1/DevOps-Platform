# S3 backend with native locking, configured at init time from the repo
# variables, never committed:
#   terraform init -backend-config="bucket=$TFSTATE_BUCKET" -backend-config="region=$AWS_REGION"
terraform {
  backend "s3" {
    key          = "dev/terraform.tfstate"
    use_lockfile = true
  }
}
