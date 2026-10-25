# Roadmap

What exists, what comes next, and what is deliberately later. Dates are
when something was verified live on the laptop this project runs on.

## Now (verified)

- Self-service path: catalog type to pull request to plan, policy, cost
  and security checks to auto-merge to one-click approval to an apply
  inside the cluster, with an audit timeline (2026-10-24).
- Incident agent: alert to diagnosis to a one-line fix as a pull request,
  propose-only by three independent locks; traces, audit, dashboards,
  evals and SLO alerts around it (2026-10-25).
- A tenant app from its own repository (Playground Bank), its namespace
  requested through the platform, its incident fixed by the agent from
  real logs (2026-10-25).
- The repository's own GitHub settings as Terraform (2026-10-25).
- Seven runbooks, one per alert family, each matched by a test to the
  recorded scenarios it serves (2026-10-26).

## Next

- README as a product document with the golden path recorded, a
  contribution guide and this roadmap (Phase 4, in progress).
- A five-minute demo script and recording.
- The eval suite on Claude in CI once an API key with a spend cap exists;
  the full local suite rerun after the folder-hint change (6 of 13 pass on
  the local 4B model today, with the failures understood).
- Run closure that waits for the incident to end, not for one flapping
  alert to resolve.

## Later

- Real AWS through GitHub OIDC for `envs/dev` (`REAL_AWS=1`), with a
  billing alert first; a short EKS run for screenshots.
- Datadog export from the OpenTelemetry collector as a configuration
  switch.
- The tenant app's Playwright smoke test run in-cluster by the platform
  (today: an HTTP smoke test that checks the same facts).
- A second agent (capacity or cost advisor) on the same runtime, to prove
  "add an agent in 20 minutes" with something other than incidents.
- Applying the GitHub settings from CI once state moves to a cloud backend.
