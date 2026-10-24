# 0007. Tools come from MCP servers; the platform writes the guard, not the tools

- Status: accepted
- Date: 2026-10-24
- Deciders: Asaf

## Context

The agent needs to read pods, logs, events, metrics and git, and to open
a pull request. Writing those tools by hand means maintaining Kubernetes,
GitHub and Grafana clients; it also makes "what can the agent do" a
question about our code rather than about a declared list.

## Decision

Tools are Model Context Protocol servers run as subprocesses inside the
agent-runtime pod, declared in `agents/tools/mcp.yaml`: the Kubernetes
server (community, npm), GitHub's official server and Grafana's official
server (Go binaries), plus a tiny local `git_log`. What the platform writes
is the layer around them:

- `agents/tools/capabilities.yaml` labels every tool `read`, `write` or
  `delete` on a target (`cluster`, `github`, `observability`, `local`). A
  tool without a label is an error, not a default.
- Each agent's manifest lists the tools it may use, as `<server>.<tool>`.
  The runtime validates the list against the labels at startup.
- One wrapper (`GuardedToolset`) sits on every call: namespace scope for
  cluster tools, branch rules for GitHub tools, an audit event and an
  OpenTelemetry span. Refusals are returned to the model as text so it
  can adapt instead of crashing the run.

## Consequences

- Adding a tool is a line in the allowlist plus a label; adding a server
  is an entry in `mcp.yaml` and a block of labels.
- The servers' own flags (`ALLOW_ONLY_NON_DESTRUCTIVE_TOOLS`,
  `--disable-write`, `--toolsets`) are hygiene, not the boundary: the
  Kubernetes server's "non-destructive" mode still allows create and
  update, which the allowlist and RBAC exclude.
- Tool names reach the model prefixed (`kubernetes_kubectl_get`), the
  policy speaks in `kubernetes.kubectl_get`; the registry maps between
  them.
- Three subprocesses start per run (a few seconds); acceptable for an
  incident agent, and the runtime serialises runs because the local model
  is CPU-bound.

## Alternatives considered

- Hand-written tools: full control, but every tool is code to maintain
  and the capability declaration would be implicit.
- A single "run kubectl" tool: the simplest, and impossible to label or
  scope honestly.
- Kubernetes MCP servers that run in-cluster as services: possible later;
  subprocesses keep the trust boundary inside one pod with one
  ServiceAccount.
