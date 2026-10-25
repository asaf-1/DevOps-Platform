"""Promptfoo provider: run one recorded scenario through the real agent.

Promptfoo calls `call_api` once per test with the fixture path in
`context["vars"]["fixture"]`. The output is the JSON record from
`runtime.evalrun.run_fixture`; `asserts.py` judges it.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
AGENTS = HERE.parent
sys.path.insert(0, str(AGENTS))
os.environ.setdefault("AGENTS_DIR", str(AGENTS))

from runtime.evalrun import run_fixture  # noqa: E402


def call_api(
    prompt: str, options: dict[str, Any] | None = None, context: dict[str, Any] | None = None
) -> dict[str, Any]:
    path = ((context or {}).get("vars") or {}).get("fixture") or prompt.strip()
    p = Path(path)
    if not p.is_absolute():
        p = HERE / p
    try:
        record = run_fixture(p)
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"}
    usage = record.get("usage") or {}
    return {
        "output": json.dumps(record, default=str),
        "tokenUsage": {
            "total": usage.get("total_tokens") or 0,
            "prompt": usage.get("input_tokens") or 0,
            "completion": usage.get("output_tokens") or 0,
        },
    }
