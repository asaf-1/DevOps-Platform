#!/usr/bin/env bash
# evals: run the incident-triage agent against every recorded scenario in
# agents/evals/fixtures with promptfoo. No cluster, no GitHub: the fixtures
# stand in for the tools (EVAL_MODE). Locally on Ollama (slow, free); in CI
# on Claude when ANTHROPIC_API_KEY is set (ADR 0009).
#
#   make evals                                  # all scenarios
#   scripts/evals.sh --filter-pattern oom       # a subset (promptfoo flags pass through)
#   promptfoo view                              # browse the last results
source "$(dirname "$0")/lib.sh"

need promptfoo
AG="$REPO_ROOT/agents"
[ -x "$AG/.venv/bin/python" ] || die "agents/.venv missing: cd agents && python -m venv .venv && .venv/bin/pip install -e '.[dev]'"

export PROMPTFOO_PYTHON="$AG/.venv/bin/python"
export AGENTS_DIR="$AG"
export MODEL_PROVIDER="${MODEL_PROVIDER:-ollama}"
export OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://host.docker.internal:11434}"
export EVAL_DB="${EVAL_DB:-/tmp/agent-evals.db}"
# One scenario takes 5 to 10 minutes on a CPU model; promptfoo kills a Python
# provider after REQUEST_TIMEOUT_MS (default 5 minutes).
export REQUEST_TIMEOUT_MS="${REQUEST_TIMEOUT_MS:-1800000}"
rm -f "$EVAL_DB"

count="$(ls "$AG/evals/fixtures"/*.yaml | wc -l | tr -d ' ')"
say "make evals: $count scenarios, model $MODEL_PROVIDER:${MODEL_NAME:-default}, one at a time (minutes each on a CPU model)"
cd "$AG/evals"
promptfoo eval -c promptfooconfig.yaml --no-cache -j 1 "$@"
