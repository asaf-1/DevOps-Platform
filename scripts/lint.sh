#!/usr/bin/env bash
# lint: everything that must be green before a push. Runs inside the
# devcontainer. Exit code is non-zero if any check fails.
#   - ruff (format + lint) on platform/api and platform/cli
#   - pytest on both
#   - terraform fmt -check and validate on modules and envs
#   - conftest verify on the policy set
#   - bash -n on every script
source "$(dirname "$0")/lib.sh"

need terraform conftest

fail=0
step() { printf '\n==> %s\n' "$*"; }
check() { if "$@"; then say "ok"; else warn "FAILED: $*"; fail=1; fi; }

PY="$REPO_ROOT/platform/api/.venv/bin"
if [ -x "$PY/ruff" ]; then
  step "ruff format --check (api, cli)"
  check "$PY/ruff" format --check "$REPO_ROOT/platform/api" "$REPO_ROOT/platform/cli"
  step "ruff check (api, cli)"
  check "$PY/ruff" check "$REPO_ROOT/platform/api" "$REPO_ROOT/platform/cli"
  step "pytest platform/api"
  check bash -c "cd '$REPO_ROOT/platform/api' && '$PY/pytest' -q"
  step "pytest platform/cli"
  check bash -c "cd '$REPO_ROOT/platform/cli' && '$PY/pytest' -q"
else
  warn "platform/api/.venv not found; skipping Python checks (see platform/api/README.md)"
fi

step "terraform fmt -check"
check terraform fmt -check -recursive "$REPO_ROOT/infra/terraform"

for env_dir in "$REPO_ROOT"/infra/terraform/envs/*/; do
  step "terraform validate $(basename "$env_dir")"
  check bash -c "cd '$env_dir' && terraform init -backend=false -input=false >/dev/null && terraform validate -no-color"
done

step "conftest verify (policy unit tests)"
check conftest verify -p "$REPO_ROOT/infra/policies/terraform" -d "$REPO_ROOT/infra/policies/terraform/tests/fixtures"

step "bash -n scripts/*.sh .devcontainer/*.sh"
check bash -c 'for f in "$0"/scripts/*.sh "$0"/.devcontainer/*.sh; do bash -n "$f" || exit 1; done' "$REPO_ROOT"

if command -v shellcheck >/dev/null 2>&1; then
  step "shellcheck"
  check shellcheck -x "$REPO_ROOT"/scripts/*.sh
fi

echo
if [ "$fail" -eq 0 ]; then say "all green"; else die "lint failed"; fi
