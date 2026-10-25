"""Nightly export of the audit trail to a bucket, as JSONL (LocalStack locally).

    python -m platform_api.export_audit                 # the last 24 hours
    AUDIT_EXPORT_SINCE_HOURS=720 python -m ...          # the last 30 days

Environment: DATABASE_URL; AUDIT_EXPORT_BUCKET (default platform-audit);
AWS_ENDPOINT_URL for LocalStack, plus the usual AWS credential variables
(dummy values for LocalStack). The bucket is created when missing. One
object per export: audit/<yyyy>/<mm>/<dd>/audit-<timestamp>.jsonl, one event
per line, keys sorted, so the file diffs and greps well.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

from .storage import Store, make_engine


def export(store: Store, s3: Any, bucket: str, since: datetime, now: datetime | None = None) -> str:
    """Write the events since `since` to `bucket` and return the object key."""
    now = now or datetime.now(UTC)
    events = store.list_events_since(since)
    lines = [json.dumps(e.model_dump(mode="json"), sort_keys=True) for e in events]
    body = ("\n".join(lines) + "\n") if lines else ""
    key = f"audit/{now:%Y/%m/%d}/audit-{now:%Y%m%dT%H%M%SZ}.jsonl"
    try:
        s3.head_bucket(Bucket=bucket)
    except Exception:  # noqa: BLE001  (botocore raises ClientError; a fake may raise anything)
        s3.create_bucket(Bucket=bucket)
    s3.put_object(
        Bucket=bucket, Key=key, Body=body.encode("utf-8"), ContentType="application/x-ndjson"
    )
    print(f"exported {len(events)} events since {since:%Y-%m-%d %H:%M} UTC to s3://{bucket}/{key}")
    return key


def main() -> int:
    import boto3
    from botocore.config import Config

    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is not set", file=sys.stderr)
        return 2
    hours = float(os.environ.get("AUDIT_EXPORT_SINCE_HOURS", "24"))
    s3 = boto3.client(
        "s3",
        endpoint_url=os.environ.get("AWS_ENDPOINT_URL") or None,
        region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
        config=Config(s3={"addressing_style": "path"}),  # bucket in the path: works with LocalStack
    )
    store = Store(make_engine(url))
    export(
        store,
        s3,
        os.environ.get("AUDIT_EXPORT_BUCKET", "platform-audit"),
        datetime.now(UTC) - timedelta(hours=hours),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
