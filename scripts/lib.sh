#!/usr/bin/env bash
# Shared helpers for scripts/. Source it: source "$(dirname "$0")/lib.sh"
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export REPO_ROOT
CLUSTER_NAME="${KIND_CLUSTER_NAME:-platform}"
export CLUSTER_NAME

say()  { printf '==> %s\n' "$*"; }
warn() { printf 'WARN: %s\n' "$*" >&2; }
die()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

# need <cmd>...: fail early with a clear message if a tool is missing.
need() {
  local missing=0
  for c in "$@"; do
    command -v "$c" >/dev/null 2>&1 || { warn "missing command: $c"; missing=1; }
  done
  [ "$missing" -eq 0 ] || die "install the missing tools (see PLAN.md section 8) or run inside the devcontainer"
}

# not_yet <phase>: placeholder for scripts implemented in a later phase.
not_yet() {
  die "not implemented yet; this arrives in $1 (see PLAN.md section 7)"
}

# in_container: true when running inside the devcontainer (or any container).
in_container() { [ -f /.dockerenv ] || [ -n "${REMOTE_CONTAINERS:-}" ]; }
