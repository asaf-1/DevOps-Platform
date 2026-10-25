# Kyverno policies

Cluster policies, applied by ArgoCD (`gitops/argocd/apps/policies.yaml`)
to the `platform` kind cluster. All are `Enforce`: a resource that breaks
one is refused at admission, and the existing resources are reported in
Kyverno's policy reports (`kubectl get policyreport -A`).

| Policy | Scope | What it refuses |
|---|---|---|
| `require-resources` | Deployments, StatefulSets, DaemonSets, Jobs, CronJobs in `demo`, `platform` and `bank` | a container without CPU and memory requests and a memory limit |
| `disallow-latest-tag` | Pods in `demo`, `platform` and `bank` (and their controllers) | an image without a tag, or with the tag `latest` |
| `require-team-label` | Deployments, StatefulSets, DaemonSets, CronJobs in `demo`, `platform` and `bank` | a workload without a `team` label |
| `deny-agent-runtime-writes` | every request by the ServiceAccount `platform/agent-runtime`, cluster-wide | any create, update, delete or connect: the third lock on propose-only agents (ADR 0008) |

Tests: `kyverno test infra/policies/kyverno/tests` runs the three
resource policies against good and bad resources (`make lint` runs it when
the Kyverno CLI is installed). The service-account policy needs a real
request and is verified live: bind the agent's ServiceAccount to `edit` for
a minute, try to create a ConfigMap as it, and read the denial.
