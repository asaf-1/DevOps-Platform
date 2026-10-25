"""Promptfoo assertion: the fixture's `expect` block against the run record."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from runtime.evalrun import verdict  # noqa: E402


def get_assert(output: Any, context: dict[str, Any] | None = None) -> dict[str, Any]:
    record = json.loads(output) if isinstance(output, str) else output
    failures = verdict(record)
    if failures:
        return {"pass": False, "score": 0.0, "reason": "; ".join(failures)}
    return {
        "pass": True,
        "score": 1.0,
        "reason": (
            f"{record.get('steps')} tool calls, {record.get('duration_s')}s, "
            f"{(record.get('usage') or {}).get('total_tokens')} tokens"
        ),
    }
