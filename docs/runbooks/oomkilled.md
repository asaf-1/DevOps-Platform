---
title: Container OOMKilled
tags: [kubernetes, oom, crashloop, demo-app]
---

# Container OOMKilled (and the CrashLoopBackOff that follows)

**What it means.** The container used more memory than its limit, the
kernel killed it, Kubernetes restarted it, and it will happen again until
the limit or the usage changes. After a few restarts the pod shows
`CrashLoopBackOff` with `Last State: Terminated, Reason: OOMKilled`.

**Causes.**
1. The memory limit in the Deployment is too small for the process. A
   Python web process needs at least about 32Mi just to start; `16Mi` or
   less is always wrong.
2. A real leak or a traffic spike (usage grows over time; check the
   `container_memory_working_set_bytes` metric before the kill).

**How to confirm.**
- `kubectl describe pod <pod> -n <ns>`: `Last State: Terminated`,
  `Reason: OOMKilled`, `Exit Code: 137`, and `Limits: memory: <value>`.
- `kubectl get deployment <app> -n <ns> -o yaml`: the `resources.limits.memory`
  value in the running spec, which mirrors git.
- Prometheus: `container_memory_working_set_bytes{namespace="<ns>",container="<app>"}`.

**Fix.** Raise `resources.limits.memory` in
`gitops/apps/<app>/deployment.yaml` to a value above the observed usage
with headroom (for the demo app, `64Mi` is the known-good value). Keep the
request at or below the limit. Change only the limit line unless usage
shows a leak, in which case say so and do not propose a limit increase as
the fix.
