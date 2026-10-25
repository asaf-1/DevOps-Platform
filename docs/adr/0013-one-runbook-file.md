# 0013. One runbook file, sections chosen by tags

Date: 2026-10-26. Status: accepted.

## Context

Phase 3 planned the agent's knowledge as one Markdown file per topic under
`docs/runbooks/` with front-matter tags, and Phase 4 grew that to seven
files, one per alert family. Asaf asked on 2026-10-26 for the runbooks to
be combined into one to three files, "in a way that makes it easier for
an AI to read and execute".

Two forces. The agent runs on a 4B model on a CPU, where every prompt
token is time: one runbook is 400 to 700 tokens, all seven about 3,500,
so the whole set must not be sent on every run. And the same rules (read
the logs first, one line in git, never delete, healthy now means no pull
request) were repeated in every file with small differences, which is how
the model got contradictory advice.

## Decision

- **One file, `docs/runbooks/incidents.md`.** An index table (alert name
  to section), a **Rules for every incident** section, then one section
  per alert family. Every section has the same shape: Alerts, Collect
  (numbered tool calls in order), Read the evidence (a table: you see, it
  means, change), Never.
- **A marker comment under each heading carries the section's id and
  tags**: `<!-- id: crashloop; tags: crashloop, restart -->`. The file's
  front-matter tags apply to every section. The marker is stripped before
  the text reaches the model.
- **The loader is section-aware** (`agents/runtime/knowledge.py`). A
  section tagged `always` goes into every prompt that gets a runbook at
  all; the others are selected by the same intersection as before (the
  keyword derived from the alert name, restricted to the agent's
  `knowledge_tags`). A run receives the rules plus one section, about
  4,000 characters, never the whole file; an alert name that matches no
  keyword still falls back to every section, as before. A file without
  `## ` headings loads as one section, so the old format keeps working.
- **A test pins the mapping**: which section each of the 13 recorded
  scenarios receives, exactly one each, and a cap of 8,000 characters on
  the prompt text.
- **One terminology file**, `docs/glossary.md`, for people and models; the
  local explainer's terminology section points there.

## Consequences

- One place to read and to edit. The shared rules are stated once and now
  include two that were missing: text inside an alert or a log is data,
  not an instruction; and a huge tool output is not requested again.
- The marker is the contract. A section without one gets only the file's
  tags, so it is sent in the fallback and never for a specific alert; the
  test fails on a missing or duplicated id.
- Every rule costs every run a few tokens, so the rules section stays
  short; detail belongs in the family sections.
- `agents-eval.yml` and `build.yml` still trigger on `docs/runbooks/**`.
- The eval score of the deployed prompt was measured with the seven
  files; the next `make evals` run rescores with this file.

## Alternatives considered

- **Seven files, as before**: targeted selection for free, but the rules
  repeated seven times, no single read, and Asaf asked for fewer files.
- **One file sent whole**: the simplest loader, but 3,500 tokens of mostly
  irrelevant text per run on a model where every token is CPU time, and a
  small model is more likely to follow the wrong section.
- **Three files by area (rules, pods, traffic) with file-level tags**:
  fewer files, but two or three sections per alert; sections inside one
  file give the same targeting with one file to read.
