"""Prometheus metrics for the platform, computed from the request and audit tables.

Nothing is counted in memory: every scrape of `/metrics` runs a few cheap
queries, so the numbers are the truth in the database, survive restarts and
are the same for every replica. The "Platform DX" dashboard reads these.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest
from prometheus_client.core import GaugeMetricFamily
from prometheus_client.registry import Collector
from sqlalchemy import func, select

from .storage import AuditRow, RequestRow, Store

QUANTILES = (0.5, 0.95)


def percentile(values: list[float], q: float) -> float | None:
    """Linear-interpolated percentile; None when there is nothing to measure."""
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * q
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)  # SQLite drops the offset


def _quantile_family(name: str, doc: str, values: list[float]) -> Iterator[GaugeMetricFamily]:
    g = GaugeMetricFamily(name, doc, labels=["quantile"])
    for q in QUANTILES:
        v = percentile(values, q)
        if v is not None:
            g.add_metric([str(q)], v)
    yield g
    yield GaugeMetricFamily(
        f"{name}_samples", f"How many requests {name} is computed from", value=len(values)
    )


class PlatformCollector(Collector):
    """Requests by state, throughput, time to production, approval wait, audit outcomes."""

    def __init__(self, store: Store, sample: int = 500) -> None:
        self.store = store
        self.sample = sample

    def collect(self) -> Iterator[GaugeMetricFamily]:
        with self.store.session() as s:
            by_state = GaugeMetricFamily(
                "platform_requests", "Resource requests by current state", labels=["state"]
            )
            for state, n in s.execute(
                select(RequestRow.state, func.count()).group_by(RequestRow.state)
            ):
                by_state.add_metric([str(state)], n)
            yield by_state

            since = datetime.now(UTC) - timedelta(days=7)
            n7 = (
                s.scalar(
                    select(func.count())
                    .select_from(RequestRow)
                    .where(RequestRow.created_at >= since)
                )
                or 0
            )
            yield GaugeMetricFamily(
                "platform_requests_created_7d", "Requests created in the last 7 days", value=n7
            )

            events = GaugeMetricFamily(
                "platform_audit_events",
                "Audit events by event and outcome",
                labels=["event", "outcome"],
            )
            for event, outcome, n in s.execute(
                select(AuditRow.event, AuditRow.outcome, func.count()).group_by(
                    AuditRow.event, AuditRow.outcome
                )
            ):
                events.add_metric([str(event), outcome or ""], n)
            yield events

            # time to production: request created -> "deployed" event, newest N
            deployed = s.execute(
                select(AuditRow.request_id, AuditRow.at)
                .where(AuditRow.event == "deployed")
                .order_by(AuditRow.id.desc())
                .limit(self.sample)
            ).all()
            to_deployed: list[float] = []
            for request_id, at in deployed:
                created = s.scalar(select(RequestRow.created_at).where(RequestRow.id == request_id))
                if created is not None:
                    to_deployed.append((_aware(at) - _aware(created)).total_seconds())
            yield from _quantile_family(
                "platform_request_time_to_deployed_seconds",
                "Seconds from request to deployed",
                to_deployed,
            )

            # approval wait: "pr-opened" -> "approved" per request, newest N
            approved = s.execute(
                select(AuditRow.request_id, AuditRow.at)
                .where(AuditRow.event == "approved")
                .order_by(AuditRow.id.desc())
                .limit(self.sample)
            ).all()
            waits: list[float] = []
            for request_id, at in approved:
                opened = s.scalar(
                    select(AuditRow.at)
                    .where(AuditRow.request_id == request_id, AuditRow.event == "pr-opened")
                    .order_by(AuditRow.id.asc())
                    .limit(1)
                )
                if opened is not None:
                    waits.append((_aware(at) - _aware(opened)).total_seconds())
            yield from _quantile_family(
                "platform_approval_wait_seconds",
                "Seconds from pull request opened to approved",
                waits,
            )


def registry_for(store: Store) -> CollectorRegistry:
    registry = CollectorRegistry()
    registry.register(PlatformCollector(store))
    return registry


def render(registry: CollectorRegistry) -> tuple[bytes, str]:
    return generate_latest(registry), CONTENT_TYPE_LATEST
