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
free, `qwen3:4b` on this laptop's CPU), `MODEL_PROVIDER=anthropic` uses
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
- Thinking models (qwen3) are asked not to think aloud (`/no_think`) to
  keep tool loops short; the switch lives in the runner, per provider.

## Alternatives considered

- Claude Agent SDK: the best tool loop for Claude, but it is Claude-only
  and the point here is the model-agnostic design with a free local path.
- LangGraph: more machinery (graphs, state) than a single triage agent
  needs; the manifest and the guard are the structure here.
- Direct provider SDKs: would duplicate tool-calling plumbing for every
  provider.
