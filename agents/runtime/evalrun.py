"""Run one fixture through the real agent and judge the result.

    python -m runtime.evalrun evals/fixtures/imagepullbackoff.yaml          # JSON record
    python -m runtime.evalrun evals/fixtures/imagepullbackoff.yaml --check  # failures, exit 1

The record has everything an assertion needs: status, tool calls (refused
ones too), the report, the proposals the agent made (branches, line
changes, pull requests) and usage. `verdict` turns the fixture's `expect`
block into a list of failures; promptfoo and `make evals` both use it.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine

from .audit import Store
from .runner import build_runner, new_run_id
from .tools.fixture import Fixture


def run_fixture(path: str | Path) -> dict[str, Any]:
    fixture = Fixture.load(path)
    db = os.environ.get("EVAL_DB") or str(Path(tempfile.gettempdir()) / "agent-evals.db")
    store = Store(create_engine(f"sqlite:///{db}"))
    runner = build_runner(store)
    run_id = new_run_id()
    alert = fixture.alert
    fingerprint = str(alert.get("fingerprint") or run_id)
    store.create_run(run_id, runner.spec.manifest.name, fingerprint, alert)
    started = time.monotonic()
    run = asyncio.run(runner.run(run_id, alert, fixture=fixture))
    steps = run.get("steps") or []
    return {
        "fixture": fixture.name,
        "run_id": run_id,
        "status": run.get("status"),
        "error": run.get("error"),
        "steps": len(steps),
        "tools": [s.get("tool") for s in steps],
        "refused": [s.get("tool") for s in steps if s.get("refused")],
        "errors": [s.get("tool") for s in steps if not s.get("ok") and not s.get("refused")],
        "report": run.get("report") or "",
        "pr_url": run.get("pr_url"),
        "usage": run.get("usage") or {},
        "proposals": fixture.proposals,
        "duration_s": round(time.monotonic() - started, 1),
        "expect": fixture.expect.model_dump(),
    }


def verdict(record: dict[str, Any]) -> list[str]:
    """Failures of a record against its fixture's `expect`; empty means pass."""
    exp = record.get("expect") or {}
    failures: list[str] = []
    report = (record.get("report") or "").lower()
    tools = record.get("tools") or []
    changes = (record.get("proposals") or {}).get("changes") or []
    prs = (record.get("proposals") or {}).get("prs") or []

    if record.get("status") != exp.get("status", "done"):
        failures.append(
            f"status {record.get('status')!r}, expected {exp.get('status')!r}: "
            f"{record.get('error')}"
        )
    for kw in exp.get("keywords") or []:
        if kw.lower() not in report:
            failures.append(f"report lacks keyword {kw!r}")
    anys = exp.get("keywords_any") or []
    if anys and not any(kw.lower() in report for kw in anys):
        failures.append(f"report has none of {anys}")
    if exp.get("no_change") and changes:
        failures.append(
            f"agent changed files although none was expected: {[c['path'] for c in changes]}"
        )
    if exp.get("changed_file"):
        paths = {c["path"] for c in changes}
        if paths != {exp["changed_file"]}:
            failures.append(f"changed files {sorted(paths)}, expected only {exp['changed_file']!r}")
    if exp.get("replace_contains"):
        if not any(exp["replace_contains"] in c.get("replace", "") for c in changes):
            failures.append(f"no change replaces with text containing {exp['replace_contains']!r}")
    if exp.get("pr") and not prs:
        failures.append("no pull request opened")
    if exp.get("no_change") and prs:
        failures.append("a pull request was opened although no change was expected")
    for tool in exp.get("forbidden_tools") or []:
        if tool in tools:
            failures.append(f"forbidden tool called: {tool}")
    if record.get("steps", 0) > int(exp.get("max_steps", 10)):
        failures.append(f"{record.get('steps')} tool calls, more than {exp.get('max_steps')}")
    return failures


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 2
    check = "--check" in argv
    paths = [a for a in argv if not a.startswith("--")]
    failed = 0
    for p in paths:
        record = run_fixture(p)
        if check:
            failures = verdict(record)
            status = "PASS" if not failures else "FAIL"
            print(
                f"{status} {record['fixture']}: {record['steps']} tool calls, "
                f"{record['duration_s']}s, status {record['status']}"
            )
            for f in failures:
                print(f"  - {f}")
            failed += bool(failures)
        else:
            print(json.dumps(record, indent=2, default=str))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
