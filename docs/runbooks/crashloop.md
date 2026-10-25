---
title: Pod in CrashLoopBackOff
tags: [kubernetes, crashloop, demo-app]
---

# Pod in CrashLoopBackOff

**What it means.** The container starts, exits, and Kubernetes restarts it
with growing delays. The reason is in the container's last exit, not in
the restart.

**Is it still broken?** `kubectl get pods -n <ns>`: a pod that is
`Running`, `Ready` and has not restarted in the last few minutes is
healthy now; the alert came from a finished rollout or a crash that
already stopped. Report that no change is needed and open no pull
request. Only a pod that is restarting now needs a fix.

**Find the reason first.**
- `kubectl describe pod <pod> -n <ns>`: `Last State`, `Reason`, `Exit Code`.
  - `OOMKilled` / exit 137: see the OOMKilled runbook.
  - `Error` / exit 1 or 2: the process failed; read its logs.
  - `ContainerCannotRun`: wrong command or missing binary in the image.
- `kubectl logs <pod> -n <ns> --previous`: the output of the crashed run.
  Look at the last 20 lines.
- `kubectl get events -n <ns> --sort-by=.lastTimestamp`.

**Read the logs before choosing a fix.** The last log lines name the
cause; the fix must match them, not the alert name:
- `listen EADDRNOTAVAIL`, `getaddrinfo ENOTFOUND <value>`, `EADDRINUSE`,
  "Server failed to start on <host>:<port>": the app cannot bind its
  address. The cause is the HOST or PORT setting (a ConfigMap, or the
  `configMapGenerator` literals in the app's `kustomization.yaml`). Set
  HOST back to `0.0.0.0` or PORT to the container port. Memory has
  nothing to do with it.
- "database failed to start", `ECONNREFUSED`, "password authentication
  failed": the DATABASE_URL or the database itself; check the Secret and
  the database pod.
- A memory limit is only the fix when `Last State` says `OOMKilled`
  (exit code 137). An `Error` with exit code 1 is never a memory problem.

**Typical fixes, all in git.**
- Configuration the app rejects (missing env, bad value): fix the
  ConfigMap, the `configMapGenerator` literals or the Deployment env in
  `gitops/apps/<app>/`.
- A probe that fails too early: raise `initialDelaySeconds` on the probe.
- A bad image: see the ImagePullBackOff runbook.

Never `kubectl delete` or restart pods by hand; the fix is a change to the
file in git, and ArgoCD rolls it out.
