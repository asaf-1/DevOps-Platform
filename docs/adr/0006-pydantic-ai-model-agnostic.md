# 0006. Pydantic AI, with the model chosen by configuration

- Status: accepted
- Date: 2026-10-24
- Deciders: Asaf

## Context

The agents need a model for every reasoning step and tool decision, and
the eval suite runs them many times per change. The project must run for
free on a laptop with no GPU, and must show the same agent on a hosted
frontier model for the demo. The job post names agent frameworks in
general, not one in particular.

## Decision

Pydantic AI is the agent framework. The model comes from
`agents/runtime/providers.py`, the only module that imports a provider:
`MODEL_PROVIDER=ollama` uses Ollama's OpenAI-compatible endpoint (local,
free, `qwen3:4b-instruct` on this laptop's CPU), `MODEL_PROVIDER=anthropic` uses
Claude (`claude-sonnet-5-5` by default) through `ANTHROPIC_API_KEY`.
Nothing else in the runtime knows which one is in use. Tool calling, typed
tool schemas, usage limits (`max_steps`, `token_budget` from the manifest)
and OpenTelemetry instrumentation come from the framework.

## Consequences

- One environment variable switches the whole agent platform between a
  free local model and Claude; the demo shows both.
- On this laptop the local model runs at about 7 tokens/s, so manifests
  keep steps and budgets small and prompts short; evals (Phase 3) are
  slow but free and have no rate limits.
- Pydantic AI 2.x changed its MCP API from 1.x (`MCPToolset` over a
  FastMCP client); the version is pinned (2.61.0) and the registry is the
  only place that touches it.
- Thinking is switched off through the only switch Ollama's OpenAI
  endpoint honours, `reasoning_effort="none"`; it ignores `tool_choice`
  and a `think` field (ollama/openai/openai.go).

## Amendment 2026-10-25: the local model is `qwen3:4b-instruct`

The library tag `qwen3:4b` resolves to Qwen3-4B-Thinking-2507, a model
that always reasons first: its chat template opens a `<think>` block on
every turn and there is no switch to close it (`/no_think` is ignored).
On this CPU it wrote 2,000+ reasoning tokens at 3 tokens/s before its
first tool call, so three live runs timed out with zero steps. The
non-reasoning sibling `qwen3:4b-instruct` (Qwen3-4B-Instruct-2507, same
size, tool calling built in) is the default instead. Two more changes
came out of the same investigation: the final answer is a typed
`IncidentReport` output tool, so every turn is a tool call and the report
has fields that evals can check; and `agents/dryrun.py` runs the real
agent against stub tools so model behaviour is checked in minutes, offline,
before a live run.

## Alternatives considered

- Claude Agent SDK: the best tool loop for Claude, but it is Claude-only
  and the point here is the model-agnostic design with a free local path.
- LangGraph: more machinery (graphs, state) than a single triage agent
  needs; the manifest and the guard are the structure here.
- Direct provider SDKs: would duplicate tool-calling plumbing for every
  provider.
