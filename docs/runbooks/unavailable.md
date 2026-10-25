---
title: Workload unavailable or pod not ready
tags: [kubernetes, unavailable, service, endpoints, eviction, demo-app]
---

# Workload unavailable or pod not ready

**What it means.** The Deployment has fewer available replicas than
desired, or the Service has no endpoints, so the ingress answers 503.
Three different causes look the same from the alert; the pod status
tells them apart.

**Look at the pod status first.** `kubectl get pods -n <ns>`, then
`kubectl describe pod <pod> -n <ns>`.

1. **Pod `Running` and `Ready`, but `kubectl get endpoints <svc>` shows
   `<none>`.** The Service does not reach the pod: its `selector` does
   not match the pod labels, or its `targetPort` is not the port the
   container listens on (`kubectl describe service <svc>` shows
   `TargetPort`; the container's `Port:` is in the pod describe output
   and the log line `listening on :<port>`). Fix the one line in
   `gitops/apps/<app>/service.yaml` so `targetPort` equals the container
   port, or the selector equals the pod labels. Nothing else.
2. **Pod `Evicted`, `Pending` or `FailedScheduling` with a message about
   the node.** `The node was low on resource: memory`, a
   `memory-pressure` taint, `Insufficient memory`: the node is the
   problem, not the workload. Confirm with `kubectl describe node`
   (`MemoryPressure True`, allocated memory near 100%). Nothing in git is
   wrong; report that the node must be relieved (other workloads, node
   size) and open no pull request. Do not raise or lower this app's
   requests to work around it.
3. **Pod restarting, `CrashLoopBackOff`, or `Ready: False` with a failing
   probe.** The app is the problem: read `kubectl logs --previous` and
   follow the CrashLoopBackOff runbook. The fix is a setting line in
   git, never a memory limit unless the state says `OOMKilled`.

Never `kubectl delete` a pod or node, and never patch the live objects;
if a change is right it goes to the file in git and ArgoCD rolls it out.
