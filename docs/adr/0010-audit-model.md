# 0010. One audit table for humans, agents and the platform

Date: 2026-10-25. Status: accepted.

## Context

Phase 1 gave the platform API an audit table (`audit_events`) for request
state changes and CI results; Phase 2 made the agent runtime write to the
same table (runs, tool calls, refusals). Both services create the table
with SQLAlchemy and neither runs a migration tool. Phase 3 needs the table
to answer "who did what, to what, under which approval, and can I open the
trace", and to be trustworthy: nobody, including the services, should be
able to edit history.

## Decision

- **One table, one shape, two writers.** Columns: `id`, `at` (the plan's
  `ts`), `actor`, `actor_type` (human, agent, system), `event` (the plan's
  `action`: a request state, `plan-ok`, `merged`, `agent.tool_call`,
  `agent.run.finished` ...), `target` (what was acted on: `<type>/<name>`
  for a request, the qualified tool name for a tool call, an alert name for
  a run), `request_id`, `run_id`, `input_hash` (sha256 of the request
  inputs), `outcome` (ok, failed, refused, error, started), `approval_ref`
  (the merge commit a deployment rests on, the pull request a run proposed),
  `trace_id`, and `details` (JSON for the rest: PR URLs, reasons, usage).
- **Schema by both services, idempotently.** Each service adds the columns
  it finds missing at start (`ensure_audit_schema`), so the table that was
  born in Phase 1 grows without a migration tool. Two tables do not justify
  Alembic yet; the day a third service writes here, they do.
- **Append-only by trigger, not by grants.** CloudNativePG's application
  role owns the database, so revoking UPDATE and DELETE from it would not
  hold (an owner can grant them back). A Postgres trigger that raises on
  UPDATE and DELETE holds for every role except a superuser, which the
  services do not have. SQLite (tests) has no trigger; the test suite checks
  the schema, not the lock.
- **Nightly export.** A CronJob in the platform-api chart runs
  `python -m platform_api.export_audit` every night at 02:00: the last 24
  hours as JSONL (one event per line, keys sorted) to the bucket
  `platform-audit`, created on first use, in LocalStack locally and in real
  S3 when `REAL_AWS=1` arrives. The export is the copy an auditor can take
  away; the table stays the source of truth.

## Alternatives considered

- **Separate tables per writer.** Rejected: the whole point is one timeline
  (`platform audit` shows a request's PR, its approval, the apply, and the
  agent's proposal in one list).
- **A dedicated read-only database role for the API and the agent.**
  Would also work, but means managing a second role and password through
  CloudNativePG for every environment. The trigger is one statement and
  travels with the schema.
- **Streaming events to Loki or an event bus instead of a table.** More
  moving parts; the table already feeds the API, the CLI and (Phase 3,
  task 7) the dashboards.

## Consequences

- `platform audit` and `GET /audit` return the new fields; old rows have
  them as null.
- An agent's audit rows link to its run (`run_id`) and its trace
  (`trace_id`), so a dashboard can go from a tool call to the span.
- Anything that needs to correct history writes a new event; the trigger
  rejects edits with "audit_events is append-only".
