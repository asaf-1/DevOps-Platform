---
title: High request latency
tags: [kubernetes, latency, performance, demo-app]
---

# High request latency

**What it means.** The app answers, but slowly (p95 above the alert's
threshold). Nothing is down. Latency has many causes and most of them
are not visible from pods and git, so this runbook is mostly about
knowing what you can and cannot verify.

**What you can check with the tools you have.**
- `kubectl get pods -n <ns>` and `kubectl describe deployment <app>`:
  all replicas `Running`, `Ready`, no restarts, no recent rollout.
- `kubectl logs`: many apps log the request time and the upstream they
  waited on (for example `upstream=s3 upstream_ms=3790`). If the upstream
  time explains the request time, the cause is outside this workload.
- `kubectl describe hpa <app>`: at `maxReplicas` with CPU above target
  means the app is undersized (the autoscaler runbook); below target
  means CPU is not the cause.

**What needs tools you do not have.** Request rate, error rate, CPU
throttling, upstream latency over time and the database's own metrics
live in Grafana and Prometheus. If the alert points at a dashboard, say
that you could not read it. Do not guess a cause from the alert text.

**Rule.** With healthy pods and no evidence in git, change nothing:
report what the logs show, name the upstream if one is slow, list what
you could not verify, and open no pull request. Resource limits, replica
counts and timeouts are not to be changed on a latency alert without a
measurement that names them.
