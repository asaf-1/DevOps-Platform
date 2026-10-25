"""Audit and run storage.

Audit events go to the same `audit_events` table the platform API writes
(same columns, actor_type "agent" or "system"), so humans and agents share
one trail. Runs live in `agent_runs`. SQLite when DATABASE_URL is unset.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String, Text, create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

# Columns both services add to audit_events when missing (the table was born
# with fewer). Shared shape: ts=at, action=event, plus these.
AUDIT_EXTRA_COLUMNS = {
    "target": "VARCHAR(200)",
    "run_id": "VARCHAR(40)",
    "input_hash": "VARCHAR(64)",
    "outcome": "VARCHAR(20)",
    "approval_ref": "VARCHAR(200)",
    "trace_id": "VARCHAR(32)",
}


def ensure_audit_schema(engine: Engine) -> None:
    """Add missing audit columns and make the table append-only.

    Two services share `audit_events` and neither runs a migration tool, so
    each adds what is missing at start (idempotent). On Postgres a trigger
    refuses UPDATE and DELETE: the application role owns the table, so grants
    alone could not make it append-only.
    """
    from sqlalchemy import inspect, text

    existing = {c["name"] for c in inspect(engine).get_columns("audit_events")}
    with engine.begin() as conn:
        for name, ddl in AUDIT_EXTRA_COLUMNS.items():
            if name not in existing:
                conn.execute(text(f"ALTER TABLE audit_events ADD COLUMN {name} {ddl}"))
        if engine.dialect.name == "postgresql":
            conn.execute(
                text(
                    "CREATE OR REPLACE FUNCTION audit_events_append_only() RETURNS trigger AS $$ "
                    "BEGIN RAISE EXCEPTION 'audit_events is append-only (% refused)', TG_OP; END; "
                    "$$ LANGUAGE plpgsql"
                )
            )
            conn.execute(text("DROP TRIGGER IF EXISTS audit_events_append_only ON audit_events"))
            conn.execute(
                text(
                    "CREATE TRIGGER audit_events_append_only BEFORE UPDATE OR DELETE "
                    "ON audit_events FOR EACH ROW EXECUTE FUNCTION audit_events_append_only()"
                )
            )


def utcnow() -> datetime:
    return datetime.now(UTC)


def sqlalchemy_url(url: str) -> str:
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


class Base(DeclarativeBase):
    pass


class AuditRow(Base):
    """Same shape as platform_api.storage.AuditRow; create_all is idempotent on it."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    event: Mapped[str] = mapped_column(String(40), index=True)
    actor: Mapped[str] = mapped_column(String(100))
    actor_type: Mapped[str] = mapped_column(String(10))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # Final shape (Phase 3): what was acted on, which run and trace, the hash
    # of the request inputs, how it ended, and the approval it rests on.
    target: Mapped[str | None] = mapped_column(String(200), nullable=True)
    run_id: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    input_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(20), nullable=True)
    approval_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(32), nullable=True)


class RunRow(Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    agent: Mapped[str] = mapped_column(String(60), index=True)
    fingerprint: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(20), index=True)  # running, done, failed
    alert: Mapped[dict[str, Any]] = mapped_column(JSON)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    report: Mapped[str | None] = mapped_column(Text, nullable=True)
    pr_url: Mapped[str | None] = mapped_column(String(300), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    usage: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    closure: Mapped[str | None] = mapped_column(Text, nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(32), nullable=True)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "agent": self.agent,
            "fingerprint": self.fingerprint,
            "status": self.status,
            "alert": self.alert,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "steps": self.steps or [],
            "report": self.report,
            "pr_url": self.pr_url,
            "error": self.error,
            "usage": self.usage or {},
            "closure": self.closure,
            "trace_id": self.trace_id,
        }


class Store:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self._sessions = sessionmaker(bind=engine, expire_on_commit=False)
        Base.metadata.create_all(engine)
        self._ensure_columns()

    def _ensure_columns(self) -> None:
        """Add columns introduced after a table already existed (no migration tool)."""
        from sqlalchemy import inspect, text

        table = RunRow.__tablename__
        existing = {c["name"] for c in inspect(self.engine).get_columns(table)}
        if "trace_id" not in existing:
            with self.engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN trace_id VARCHAR(32)"))
        ensure_audit_schema(self.engine)

    @classmethod
    def from_env(cls) -> Store:
        url = sqlalchemy_url(os.environ.get("DATABASE_URL", "sqlite:///./agent-runtime.db"))
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        return cls(create_engine(url, connect_args=connect_args, future=True))

    @contextmanager
    def session(self) -> Iterator[Session]:
        with self._sessions() as s:
            yield s
            s.commit()

    # audit

    def audit(
        self,
        event: str,
        *,
        actor: str,
        actor_type: str = "agent",
        request_id: str | None = None,
        details: dict[str, Any] | None = None,
        target: str | None = None,
        outcome: str | None = "ok",
        run_id: str | None = None,
        trace_id: str | None = None,
        input_hash: str | None = None,
        approval_ref: str | None = None,
    ) -> None:
        with self.session() as s:
            s.add(
                AuditRow(
                    request_id=request_id,
                    event=event,
                    actor=actor,
                    actor_type=actor_type,
                    at=utcnow(),
                    details=details or {},
                    target=target,
                    outcome=outcome,
                    run_id=run_id,
                    trace_id=trace_id,
                    input_hash=input_hash,
                    approval_ref=approval_ref,
                )
            )

    # runs

    def create_run(
        self, run_id: str, agent: str, fingerprint: str, alert: dict[str, Any]
    ) -> dict[str, Any]:
        row = RunRow(
            id=run_id,
            agent=agent,
            fingerprint=fingerprint,
            status="running",
            alert=alert,
            started_at=utcnow(),
            steps=[],
        )
        with self.session() as s:
            s.add(row)
        return row.to_dict()

    def add_step(self, run_id: str, step: dict[str, Any]) -> None:
        with self.session() as s:
            row = s.get(RunRow, run_id)
            if row is None:
                return
            row.steps = [*(row.steps or []), step]

    def finish_run(
        self,
        run_id: str,
        *,
        status: str,
        report: str | None = None,
        pr_url: str | None = None,
        error: str | None = None,
        usage: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self.session() as s:
            row = s.get(RunRow, run_id)
            if row is None:
                raise KeyError(run_id)
            row.status = status
            row.finished_at = utcnow()
            row.report = report
            row.pr_url = pr_url
            row.error = error
            row.usage = usage or {}
            s.flush()
            return row.to_dict()

    def set_trace(self, run_id: str, trace_id: str) -> None:
        with self.session() as s:
            row = s.get(RunRow, run_id)
            if row is not None:
                row.trace_id = trace_id

    def close_run(self, run_id: str, note: str) -> None:
        with self.session() as s:
            row = s.get(RunRow, run_id)
            if row is not None:
                row.closure = note

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self.session() as s:
            row = s.get(RunRow, run_id)
            return row.to_dict() if row else None

    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        stmt = select(RunRow).order_by(RunRow.started_at.desc()).limit(limit)
        with self.session() as s:
            return [r.to_dict() for r in s.scalars(stmt)]

    def latest_run_for(self, fingerprint: str) -> dict[str, Any] | None:
        stmt = (
            select(RunRow)
            .where(RunRow.fingerprint == fingerprint)
            .order_by(RunRow.started_at.desc())
            .limit(1)
        )
        with self.session() as s:
            row = s.scalars(stmt).first()
            return row.to_dict() if row else None
