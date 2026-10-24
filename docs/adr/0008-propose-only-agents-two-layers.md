# 0008. Agents are propose-only, enforced in three independent layers

- Status: accepted
- Date: 2026-10-24
- Deciders: Asaf

## Context

An agent that can change the cluster is an incident waiting to happen; an
agent that can only propose is useful and safe. "Propose-only" must be a
property someone can verify, not a sentence in a prompt. A prompt is
advice; models ignore advice.

## Decision

The incident-triage agent may read the namespaces it is allowed and may
open a pull request against the GitOps folder. It can never change the
cluster, and that is enforced three times, each layer independent of the
others:

1. **Manifest validation** (`agents/runtime/manifest.py`): with
   `mutation: propose_only`, any allowed tool labelled `write` or `delete`
   on the cluster, or `delete` anywhere, makes the runtime refuse to start
   and log the tool. Verified by unit tests and by the Phase 2 negative
   check (add `kubernetes.kubectl_delete` and watch it refuse).
2. **Kubernetes RBAC** (`gitops/charts/agent-runtime/templates/rbac.yaml`):
   the `agent-runtime` ServiceAccount has one namespaced Role per allowed
   namespace with `get`, `list`, `watch` only, and no ClusterRole.
   `kubectl auth can-i delete pods --as=system:serviceaccount:platform:agent-runtime -n demo`
   answers `no`.
3. **Kyverno admission policy** (Phase 3): denies any write from that
   ServiceAccount even if a Role were added by mistake.

The pull request is the proposal. The agent may only write to branches
named `agent/*` and only open PRs from them to `main`; a human merges.
The run's steps, tool calls, refusals and report are in the audit trail
and in traces.

## Consequences

- Removing any one layer leaves two; a mistake in one is caught by the
  others. The demo shows each layer refusing.
- The agent's PR goes through the same CI and the same review as a human
  request; ArgoCD applies it only after the merge.
- Tools the agent would need to *act* (restart a pod, scale a deployment)
  are not available by design; the proposal says what to change in git.
- The GitHub token the agent uses can write to the repo; branch rules in
  the guard are what keep it to `agent/*`. A narrower token per agent is
  a Phase 4 improvement.

## Alternatives considered

- "Human in the loop" prompts only: not verifiable.
- A read-only token for GitHub too, with the PR opened by the platform
  API on the agent's behalf: cleaner separation, more plumbing; the guard
  achieves the same with less code and is the first thing to revisit.
- Letting the agent apply low-risk changes directly (restart a pod):
  tempting for the demo, fatal for the story.
