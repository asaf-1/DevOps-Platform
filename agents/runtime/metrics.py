"""Prometheus metrics for the agent platform, computed from the run and audit tables.

Scraped at `/metrics`; every scrape queries the database, so the numbers
survive restarts. The "Agents" dashboard reads these.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterator
from datetime import UTC, datetime

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest
from prometheus_client.core import GaugeMetricFamily
from prometheus_client.registry import Collector
from sqlalchemy import func, select

from .audit import AuditRow, RunRow, Store

QUANTILES = (0.5, 0.95)


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * q
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


class AgentCollector(Collector):
    """Runs by status, steps, tokens, duration, tool calls by tool and outcome, eval score."""

    def __init__(self, store: Store, prompt: str = "", sample: int = 200) -> None:
        self.store = store
        self.sample = sample
        self.prompt_version = (
            hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:12] if prompt else ""
        )

    def collect(self) -> Iterator[GaugeMetricFamily]:
        with self.store.session() as s:
            by_status = GaugeMetricFamily("agent_runs", "Agent runs by status", labels=["status"])
            for status, n in s.execute(select(RunRow.status, func.count()).group_by(RunRow.status)):
                by_status.add_metric([str(status)], n)
            yield by_status

            closed = s.scalar(
                select(func.count()).select_from(RunRow).where(RunRow.closure.is_not(None))
            )
            yield GaugeMetricFamily(
                "agent_runs_closed",
                "Runs whose alert resolved after the proposal",
                value=closed or 0,
            )

            recent = s.scalars(
                select(RunRow)
                .where(RunRow.status == "done")
                .order_by(RunRow.started_at.desc())
                .limit(self.sample)
            ).all()
            steps = [len(r.steps or []) for r in recent]
            tokens = [float((r.usage or {}).get("total_tokens") or 0) for r in recent]
            durations = [
                (_aware(r.finished_at) - _aware(r.started_at)).total_seconds()
                for r in recent
                if r.finished_at is not None
            ]
            yield GaugeMetricFamily(
                "agent_run_steps_mean",
                "Mean tool calls per finished run",
                value=(sum(steps) / len(steps)) if steps else 0,
            )
            yield GaugeMetricFamily(
                "agent_run_tokens_mean",
                "Mean tokens per finished run",
                value=(sum(tokens) / len(tokens)) if tokens else 0,
            )
            dur = GaugeMetricFamily(
                "agent_run_duration_seconds", "Seconds from alert to report", labels=["quantile"]
            )
            for q in QUANTILES:
                v = percentile(durations, q)
                if v is not None:
                    dur.add_metric([str(q)], v)
            yield dur

            # time to the first tool call: the agent's first response to an alert
            first: list[float] = []
            for r in recent:
                steps_list = r.steps or []
                at = steps_list[0].get("at") if steps_list else None
                if at:
                    try:
                        first.append(
                            (datetime.fromisoformat(at) - _aware(r.started_at)).total_seconds()
                        )
                    except ValueError:
                        pass
            ft = GaugeMetricFamily(
                "agent_run_first_tool_seconds",
                "Seconds from alert to the first tool call",
                labels=["quantile"],
            )
            for q in QUANTILES:
                v = percentile(first, q)
                if v is not None:
                    ft.add_metric([str(q)], v)
            yield ft

            calls = GaugeMetricFamily(
                "agent_tool_calls", "Tool calls by tool and outcome", labels=["tool", "outcome"]
            )
            for target, outcome, n in s.execute(
                select(AuditRow.target, AuditRow.outcome, func.count())
                .where(AuditRow.event.in_(("agent.tool_call", "agent.tool_refused")))
                .group_by(AuditRow.target, AuditRow.outcome)
            ):
                calls.add_metric([target or "", outcome or ""], n)
            yield calls

        info = GaugeMetricFamily(
            "agent_prompt_info", "Version (hash) of the deployed prompt", labels=["version"]
        )
        info.add_metric([self.prompt_version], 1)
        yield info
        score = os.environ.get("AGENT_EVAL_SCORE")
        if score:
            try:
                yield GaugeMetricFamily(
                    "agent_eval_score",
                    "Eval pass rate of the deployed prompt version (0 to 1), set at deploy",
                    value=float(score),
                )
            except ValueError:
                pass


def registry_for(store: Store, prompt: str = "") -> CollectorRegistry:
    registry = CollectorRegistry()
    registry.register(AgentCollector(store, prompt))
    return registry


def render(registry: CollectorRegistry) -> tuple[bytes, str]:
    return generate_latest(registry), CONTENT_TYPE_LATEST
