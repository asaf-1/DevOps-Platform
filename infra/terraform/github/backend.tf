# State lives in the platform's Postgres, like the environments, in a schema
# of its own. scripts/github-settings.sh port-forwards the cluster database
# and passes the connection string at init time; nothing is committed.
terraform {
  backend "pg" {
    schema_name = "terraform_github"
  }
}
