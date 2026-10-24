"""Persistence: requests and audit events. SQLite for local runs, Postgres in the cluster.

Audit events are the record of truth for what happened; the request row is
the current snapshot. Every state change goes through Store.transition so
the two never disagree.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String, Text, create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from .models import AuditEvent, RequestState, ResourceRequest


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class RequestRow(Base):
    __tablename__ = "requests"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    type: Mapped[str] = mapped_column(String(60))
    environment: Mapped[str] = mapped_column(String(20))
    inputs: Mapped[dict[str, Any]] = mapped_column(JSON)
    requested_by: Mapped[str] = mapped_column(String(100))
    state: Mapped[str] = mapped_column(String(20), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    branch: Mapped[str | None] = mapped_column(String(120), nullable=True)
    pr_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pr_url: Mapped[str | None] = mapped_column(String(300), nullable=True)
    outputs: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    def to_model(self) -> ResourceRequest:
        return ResourceRequest(
            id=self.id,
            type=self.type,
            environment=self.environment,
            inputs=self.inputs,
            requested_by=self.requested_by,
            state=RequestState(self.state),
            created_at=self.created_at,
            updated_at=self.updated_at,
            branch=self.branch,
            pr_number=self.pr_number,
            pr_url=self.pr_url,
            outputs=self.outputs,
            error=self.error,
        )


class AuditRow(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    event: Mapped[str] = mapped_column(String(40), index=True)
    actor: Mapped[str] = mapped_column(String(100))
    actor_type: Mapped[str] = mapped_column(String(10))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    def to_model(self) -> AuditEvent:
        return AuditEvent(
            id=self.id,
            request_id=self.request_id,
            event=self.event,
            actor=self.actor,
            actor_type=self.actor_type,  # type: ignore[arg-type]
            at=self.at,
            details=self.details or {},
        )


def make_engine(database_url: str) -> Engine:
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, connect_args=connect_args, future=True)


class Store:
    """All reads and writes. One instance per process."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self._sessions = sessionmaker(bind=engine, expire_on_commit=False)
        Base.metadata.create_all(engine)

    @contextmanager
    def session(self) -> Iterator[Session]:
        with self._sessions() as s:
            yield s
            s.commit()

    # requests

    def create_request(
        self,
        request_id: str,
        type_name: str,
        environment: str,
        inputs: dict[str, Any],
        requested_by: str,
    ) -> ResourceRequest:
        now = utcnow()
        row = RequestRow(
            id=request_id,
            type=type_name,
            environment=environment,
            inputs=inputs,
            requested_by=requested_by,
            state=RequestState.REQUESTED.value,
            created_at=now,
            updated_at=now,
        )
        with self.session() as s:
            s.add(row)
            s.add(
                AuditRow(
                    request_id=request_id,
                    event=RequestState.REQUESTED.value,
                    actor=requested_by,
                    actor_type="human",
                    at=now,
                    details={"type": type_name, "environment": environment, "inputs": inputs},
                )
            )
        return row.to_model()

    def get_request(self, request_id: str) -> ResourceRequest | None:
        with self.session() as s:
            row = s.get(RequestRow, request_id)
            return row.to_model() if row else None

    def list_requests(
        self, state: RequestState | None = None, limit: int = 100
    ) -> list[ResourceRequest]:
        stmt = select(RequestRow).order_by(RequestRow.created_at.desc()).limit(limit)
        if state is not None:
            stmt = stmt.where(RequestRow.state == state.value)
        with self.session() as s:
            return [r.to_model() for r in s.scalars(stmt)]

    def transition(
        self,
        request_id: str,
        state: RequestState,
        *,
        actor: str,
        actor_type: str = "system",
        details: dict[str, Any] | None = None,
        **fields: Any,
    ) -> ResourceRequest:
        """Move a request to a new state, set extra fields, and write the audit event."""
        now = utcnow()
        with self.session() as s:
            row = s.get(RequestRow, request_id)
            if row is None:
                raise KeyError(request_id)
            row.state = state.value
            row.updated_at = now
            for key, value in fields.items():
                setattr(row, key, value)
            s.add(
                AuditRow(
                    request_id=request_id,
                    event=state.value,
                    actor=actor,
                    actor_type=actor_type,
                    at=now,
                    details=details or {},
                )
            )
            s.flush()
            return row.to_model()

    # audit

    def add_event(
        self,
        event: str,
        *,
        actor: str,
        actor_type: str = "system",
        request_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> AuditEvent:
        """An audit event that is not a state change (e.g. plan-ok, policy-ok)."""
        row = AuditRow(
            request_id=request_id,
            event=event,
            actor=actor,
            actor_type=actor_type,
            at=utcnow(),
            details=details or {},
        )
        with self.session() as s:
            s.add(row)
            s.flush()
            return row.to_model()

    def list_events(self, request_id: str | None = None, limit: int = 500) -> list[AuditEvent]:
        stmt = select(AuditRow).order_by(AuditRow.at.asc(), AuditRow.id.asc()).limit(limit)
        if request_id is not None:
            stmt = stmt.where(AuditRow.request_id == request_id)
        with self.session() as s:
            return [r.to_model() for r in s.scalars(stmt)]
