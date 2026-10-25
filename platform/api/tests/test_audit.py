"""Audit trail: final column set, filled by transitions and events, exported as JSONL."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import inspect

from platform_api.export_audit import export
from platform_api.models import RequestState
from platform_api.storage import AUDIT_EXTRA_COLUMNS, Store, hash_inputs, make_engine


def make_store(tmp_path: Path) -> Store:
    return Store(make_engine(f"sqlite:///{tmp_path / 'a.db'}"))


def test_audit_table_has_the_final_columns(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    columns = {c["name"] for c in inspect(store.engine).get_columns("audit_events")}
    assert {"request_id", "event", "actor", "actor_type", "at", "details"} <= columns
    assert set(AUDIT_EXTRA_COLUMNS) <= columns
    # a second start on the same database is a no-op (idempotent schema step)
    Store(store.engine)


def test_transition_and_events_fill_target_outcome_hash_and_approval(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    inputs = {"name": "demo-uploads", "team": "web"}
    store.create_request("r-1", "s3-bucket", "local", inputs, "asaf")
    store.transition("r-1", RequestState.PR_OPENED, actor="platform-api")
    store.transition(
        "r-1",
        RequestState.APPROVED,
        actor="github/iac-approve",
        actor_type="human",
        approval_ref="abc1234",
    )
    store.transition("r-1", RequestState.FAILED, actor="apply-worker", error="boom")
    ev = store.add_event("plan-ok", actor="ci", request_id="r-1", target="pr/7")
    events = {e.event: e for e in store.list_events(request_id="r-1")}

    assert events["pr-opened"].target == "s3-bucket/demo-uploads"
    assert events["pr-opened"].input_hash == hash_inputs(inputs)
    assert len(events["pr-opened"].input_hash or "") == 64
    assert events["pr-opened"].outcome == "ok"
    assert events["approved"].approval_ref == "abc1234"
    assert events["failed"].outcome == "failed"
    assert ev.target == "pr/7" and ev.outcome == "ok"


class FakeS3:
    def __init__(self, buckets: set[str] | None = None) -> None:
        self.buckets = set(buckets or [])
        self.objects: dict[tuple[str, str], bytes] = {}

    def head_bucket(self, Bucket: str) -> None:  # noqa: N803
        if Bucket not in self.buckets:
            raise RuntimeError("NoSuchBucket")

    def create_bucket(self, Bucket: str) -> None:  # noqa: N803
        self.buckets.add(Bucket)

    def put_object(self, Bucket: str, Key: str, Body: bytes, **kw: Any) -> None:  # noqa: N803
        self.objects[(Bucket, Key)] = Body


def test_export_writes_one_event_per_line_and_creates_the_bucket(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.add_event("plan-ok", actor="ci", request_id="r-1")
    store.add_event("policy-ok", actor="ci", request_id="r-1")
    s3 = FakeS3()
    now = datetime(2026, 10, 26, 2, 0, tzinfo=UTC)
    key = export(store, s3, "platform-audit", now - timedelta(days=1), now=now)

    assert key == "audit/2026/10/26/audit-20261026T020000Z.jsonl"
    assert "platform-audit" in s3.buckets
    lines = s3.objects[("platform-audit", key)].decode().splitlines()
    assert [json.loads(line)["event"] for line in lines] == ["plan-ok", "policy-ok"]
    assert json.loads(lines[0])["outcome"] == "ok"


def test_export_of_an_empty_window(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    s3 = FakeS3({"platform-audit"})
    key = export(store, s3, "platform-audit", datetime.now(UTC))
    assert s3.objects[("platform-audit", key)] == b""
