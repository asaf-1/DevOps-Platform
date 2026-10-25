---
title: Autoscaler stuck at its maximum
tags: [kubernetes, hpa, autoscaling, demo-app]
---

# Autoscaler stuck at its maximum

**What it means.** The HorizontalPodAutoscaler wants more replicas than
its `maxReplicas` allows, so the pods it has stay above the CPU target.
Nothing is crashing; the app is slow because it is undersized.

**How to confirm.**
- `kubectl describe hpa <name> -n <ns>`: `Metrics` shows current versus
  target (for example `94% / 60%`), `Max replicas`, and the condition
  `ScalingLimited True TooManyReplicas`. That condition is the proof.
- `kubectl get pods -n <ns>`: the replica count equals `maxReplicas` and
  every pod is `Running`.

**Decide before changing anything.**
- Current usage above target and `ScalingLimited`: raise the ceiling.
- Usage below target: the alert is stale or noise; report no change.
- Pods restarting or not ready: that is a different problem; read their
  logs first (the CrashLoopBackOff runbook).

**Fix, in git.** The autoscaler is `gitops/apps/<app>/hpa.yaml`. Raise
the `maxReplicas:` line by a modest step (for example 3 to 5), never by
an order of magnitude; the node has limited memory and every replica
reserves its request. Change only that line. Do not touch the CPU target,
the Deployment's `replicas` or the resource requests, and never scale by
hand with `kubectl scale`: ArgoCD would revert it.
