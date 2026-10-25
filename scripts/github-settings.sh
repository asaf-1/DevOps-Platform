#!/usr/bin/env bash
# github-settings: plan (default) or apply (APPLY=1) the repository's own
# GitHub settings from infra/terraform/github. State is the platform's
# Postgres (schema terraform_github) through a port-forward opened here; the
# admin token comes from .env and is exported only for this process.
source "$(dirname "$0")/lib.sh"

need terraform kubectl
DIR="$REPO_ROOT/infra/terraform/github"
TOKEN="$(grep -E '^GITHUB_ADMIN_TOKEN=' "$REPO_ROOT/.env" 2>/dev/null | cut -d= -f2- | tr -d '"' | tr -d '[:space:]' || true)"
[ -n "$TOKEN" ] || die "GITHUB_ADMIN_TOKEN missing in .env: a fine-grained token for this repository with Administration RW, Environments RW, Issues RW, Secrets R, Metadata R (see infra/terraform/github/README.md)"

PGUSER="$(kubectl -n platform get secret platform-app -o jsonpath='{.data.username}' | base64 -d)"
PGPASS="$(kubectl -n platform get secret platform-app -o jsonpath='{.data.password}' | base64 -d)"
[ -n "$PGUSER" ] && [ -n "$PGPASS" ] || die "cannot read the platform-app Secret in namespace platform (is the cluster up?)"

say "port-forward platform/svc/platform-rw -> localhost:15432 (Terraform state)"
kubectl -n platform port-forward svc/platform-rw 15432:5432 >/dev/null 2>&1 &
PF=$!
trap 'kill $PF 2>/dev/null' EXIT
sleep 2

export PG_CONN_STR="postgres://${PGUSER}:${PGPASS}@localhost:15432/platform?sslmode=disable"
export GITHUB_TOKEN="$TOKEN"
cd "$DIR"

say "terraform init (backend pg, schema terraform_github)"
terraform init -input=false -reconfigure >/dev/null
if [ "${APPLY:-0}" = "1" ]; then
  say "terraform apply: the repository's settings become what the code says"
  terraform apply -input=false
else
  say "terraform plan (read it; APPLY=1 make github-settings applies)"
  terraform plan -input=false
fi
