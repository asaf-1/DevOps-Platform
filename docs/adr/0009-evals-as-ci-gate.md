# 0009. Agent evals as a CI gate

Date: 2026-10-25. Status: accepted.

## Context

Phase 2 ended with a live run that opened the right pull request, after
three runs that did not. Each live run costs ten to fifteen minutes on this
laptop and needs the cluster, GitHub and Alertmanager. A prompt or runbook
edit can silently change what the agent does. Phase 3's goal is that such a
change is caught before it merges, cheaply, and that the local model can
still be exercised for free.

## Decision

- **Recorded scenarios, not live runs.** `agents/evals/fixtures/*.yaml`
  hold, per scenario, the alert, the GitOps files, canned cluster outputs
  and an `expect` block. Twelve to start: nine incidents (the three live
  ones plus bad env, wrong Service port, missing ConfigMap key, node memory
  pressure, HPA at max, expired TLS secret, a noisy alert needing no
  action) and three safety cases (prompt injection asking for deletes, a
  tool outside the allowlist, output bigger than the token budget).
- **The real agent, fake tools.** With `EVAL_MODE=1` (or a fixture passed
  to the runner) the registry serves tools from the fixture instead of the
  MCP servers; the tools mirror the real names and schemas and the same
  guard sits in front of them. Nothing else in the runtime knows it is an
  eval. `agents/dryrun.py` uses the same path to show one scenario step by
  step.
- **Promptfoo runs the suite**, through a Python provider
  (`agents/evals/provider.py`) that calls `runtime.evalrun.run_fixture` and
  a Python assertion (`asserts.py`) that applies `runtime.evalrun.verdict`
  to the fixture's `expect`. Pass criterion: every scenario passes every
  assertion. `make evals` runs it locally on Ollama, one scenario at a time.
- **Two CI jobs on PRs touching `agents/` or `docs/runbooks/`.** The
  deterministic job always runs: lint, manifest validation, guard rules,
  fixture schema, the runner end to end on Pydantic AI's test model. The
  eval job runs the suite on the cheapest Claude model (`claude-haiku-5-5`)
  and only when the repo secret `ANTHROPIC_API_KEY` exists; without it the
  job is skipped with a visible notice, and `make evals` is the gate the
  developer runs by hand.

## Alternatives considered

- **A self-hosted runner on this PC so CI evals run on Ollama for free.**
  Rejected: the repository is public, and a self-hosted runner executes
  workflow code from pull requests on the laptop. GitHub itself advises
  against self-hosted runners for public repositories. Also each scenario
  takes minutes on this CPU; twelve of them would make every agent PR wait
  an hour.
- **Evals on the hosted runner with Ollama in CI.** Rejected: pulling a
  2.5 GB model and running it on a two-core runner per PR is slower still.
- **A larger local model for better scores.** Out of scope: the eval
  suite is about catching regressions, not about the ceiling of a 4B model;
  Claude is the model for the final numbers (PLAN section 9).

## Consequences

- A prompt change that regresses a scenario fails `make evals`; in CI it
  fails the eval job once the key is configured, a few cents per PR with
  the spend cap set in the Anthropic console.
- Fixtures are the agent's regression suite: a new incident type is a new
  YAML file, and a bug found live becomes a fixture first.
- The local suite is slow (about ten minutes per scenario on this laptop);
  `scripts/evals.sh --filter-pattern <name>` runs a subset.
