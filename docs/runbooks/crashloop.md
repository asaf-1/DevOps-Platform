---
title: Pod in CrashLoopBackOff
tags: [kubernetes, crashloop, demo-app]
---

# Pod in CrashLoopBackOff

**What it means.** The container starts, exits, and Kubernetes restarts it
with growing delays. The reason is in the container's last exit, not in
the restart.

**Find the reason first.**
- `kubectl describe pod <pod> -n <ns>`: `Last State`, `Reason`, `Exit Code`.
  - `OOMKilled` / exit 137: see the OOMKilled runbook.
  - `Error` / exit 1 or 2: the process failed; read its logs.
  - `ContainerCannotRun`: wrong command or missing binary in the image.
- `kubectl logs <pod> -n <ns> --previous`: the output of the crashed run.
  Look at the last 20 lines.
- `kubectl get events -n <ns> --sort-by=.lastTimestamp`.

**Typical fixes, all in git.**
- Configuration the app rejects (missing env, bad value): fix the
  ConfigMap or Deployment env in `gitops/apps/<app>/`.
- A probe that fails too early: raise `initialDelaySeconds` on the probe.
- A bad image: see the ImagePullBackOff runbook.

Never `kubectl delete` or restart pods by hand; the fix is a change to the
file in git, and ArgoCD rolls it out.
