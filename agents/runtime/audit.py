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
        """Add columns introduced after a table already existed (two tables, no migration tool)."""
        from sqlalchemy import inspect, text

        table = RunRow.__tablename__
        existing = {c["name"] for c in inspect(self.engine).get_columns(table)}
        if "trace_id" not in existing:
            with self.engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN trace_id VARCHAR(32)"))

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
