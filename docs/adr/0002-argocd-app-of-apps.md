# 0002. ArgoCD app of apps as the only way to change the cluster

- Status: accepted
- Date: 2026-10-24
- Deciders: Asaf

## Context

The cluster hosts the observability stack, policy engine, database,
LocalStack and later the platform services and the agent runtime. The job
post names ArgoCD. The agents are propose-only: they must be able to open a
pull request that changes the cluster but must never be able to change it
directly. That property is easiest to prove when git is the only input.

## Decision

`scripts/up.sh` installs exactly two things with Helm: ingress-nginx and
ArgoCD. It then applies one AppProject (`platform`) and one root
Application that syncs `gitops/argocd/apps/` from the `main` branch of the
public repo with automated sync, prune and self-heal. Every other component
is an Application in that folder. Third-party charts are multi-source
Applications: the chart comes from its Helm repository at a pinned version,
the values file comes from this repo (`gitops/clusters/local/values/`).
The AppProject lists the only allowed source repositories.

## Consequences

- The repo must be public and pushed before the root Application can sync;
  `make up` waits for it and says so when it cannot fetch.
- A change to the cluster is a commit on `main`. Self-heal reverts manual
  edits, which is what makes "the agent cannot change the cluster" a
  verifiable claim rather than a policy statement.
- Secrets are the exception: `up.sh` creates them (Grafana admin password,
  later the agent runtime's GitHub token) and the values reference them by
  name. Nothing secret is in git.
- Ordering is expressed with sync waves (operator before its custom
  resources) and retries, not with scripts.
- Large CRDs (Prometheus operator, Kyverno) need server-side apply, which
  is set per Application.
- Everything is pinned: chart versions in the Application manifests, tool
  versions in the devcontainer. Upgrades are pull requests.

## Alternatives considered

- Flux: equivalent capability; ArgoCD is named in the job post and has the
  UI that makes the demo legible.
- Helmfile or a shell script per component: simpler to start, but then the
  cluster can be changed from a laptop, which weakens the propose-only
  story.
- ApplicationSets with a generator over the apps folder: less to write per
  Application, but one explicit file per component is easier to review,
  which is the point of the exercise.
