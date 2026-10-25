# 0011. A tenant app deployed from its own repository

Date: 2026-10-25. Status: accepted.

## Context

PLAN section 7.4b makes Asaf's `asaf-1/Agents-Playground` ("Playground
Bank") the realistic workload on this platform, with a rule: the platform
never copies the app's code or manifests; it points at them at a pinned
version, and changes to the app go through that repository. The app's
`k8s/` folder has no kustomization file, ships its own Namespace, uses an
image that exists in no registry (loaded into kind by hand), runs an
embedded database unless `DATABASE_URL` is set, and allows egress to DNS
only.

## Decision

- **A kustomize overlay, not a copy.** `gitops/apps/playground-bank/`
  lists the app's manifest files by URL at a pinned commit (the raw files,
  because the folder has no kustomization) and patches only what the
  platform decides: namespace `bank`, the image, `DATABASE_URL` from a CNPG
  Secret, egress to Postgres, ClusterIP instead of NodePort, the ingress
  host `bank.localhost`, resources, the `team` label. The app's ConfigMap is
  replaced by a generator so a settings change rolls the Deployment.
- **The namespace comes from the platform.** `bank` is a `k8s-namespace`
  request through the self-service path (quota, labels, approval), not a
  `CreateNamespace` on the Application. The Application waits until the
  request is applied.
- **The database lives with the tenant.** A CNPG `Cluster` named `bank` is
  part of the overlay (not under `gitops/clusters/local/postgres/`, which
  stays the platform's own database), so the tenant's state is one
  Application.
- **The image is built from the pinned commit, in this repository's CI,
  for now.** The tenant repo publishes no app image. `build-tenant.yml`
  builds `Agents-Playground` at the commit the overlay pins and pushes
  `ghcr.io/asaf-1/devops-platform/playground-bank:sha-<7>`. The overlay's
  pin and tag must agree or the build fails. When the tenant repository
  publishes its own image (a pull request there, Asaf's call), the overlay
  points at it and this job goes away.
- **Breaking it for a demo is a settings change in git.** `make break
  BREAK_TARGET=bank` sets `HOST=0.0.0.0.1` in the overlay's ConfigMap: the
  app logs "Server failed to start ... EADDRNOTAVAIL", its health check
  fails, the `BankApp*` alerts fire, and the fix is one line in
  `gitops/apps/playground-bank/kustomization.yaml`. Defects armed through
  the app's API are in-memory and leave nothing in git for a propose-only
  agent to fix, so they stay a Playwright-side feature.
- **The smoke test is an HTTP check run by the platform.** The agent's
  `smoke_test` tool asks the platform API, which calls the app's health,
  products and orders endpoints (what the app's `test:sanity` flow checks
  through the browser). Running the Playwright suite in-cluster would need
  a browser runner Job and a repository checkout per run; too heavy for
  this laptop, recorded as a later improvement.

## Consequences

- The platform repository contains no code from the tenant; its manifests
  are fetched at build time by kustomize from the pinned commit.
- Moving the pin is a reviewed commit that changes two lines (the URLs'
  commit and `newTag`) and triggers the tenant image build.
- A second tenant follows the same shape: an overlay folder, a namespace
  request, an Application.
