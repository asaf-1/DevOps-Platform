# State lives in the platform's Postgres (CloudNativePG cluster "platform"),
# with locking, so the apply worker survives restarts and nothing depends
# on LocalStack keeping data (it does not). Connection string is supplied at
# init time, never committed:
#   terraform init -backend-config="conn_str=$PG_CONN_STR"
# or the PG_CONN_STR environment variable.
#
# CI and hand-run plans have no Postgres. They drop a gitignored
# backend_override.tf next to this file that switches to a throwaway local
# backend (see envs/README.md); every resource then shows as new.
terraform {
  backend "pg" {
    schema_name = "terraform_local"
  }
}
