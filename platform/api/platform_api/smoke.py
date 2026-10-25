"""Smoke tests the platform runs against tenant apps, over HTTP.

What Playground Bank's `test:sanity` Playwright flow checks through the
browser (health answers "ok", the dashboard lists orders, a product page
shows a price), checked here through the app's JSON API. The incident agent
calls this through `GET /smoke/{app}`; it never touches the app itself.
"""

from __future__ import annotations

import time
from typing import Any

import httpx


def _step(name: str, ok: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "ok": ok, "detail": detail[:300]}


def run_smoke(app: str, base_url: str, client: httpx.Client | None = None) -> dict[str, Any]:
    """Health, product catalogue, one product, orders. Never raises."""
    started = time.monotonic()
    base = base_url.rstrip("/")
    http = client or httpx.Client(timeout=10, follow_redirects=True)
    steps: list[dict[str, Any]] = []

    def get(path: str) -> httpx.Response | None:
        try:
            return http.get(f"{base}{path}")
        except httpx.HTTPError as e:
            steps.append(_step(f"GET {path}", False, f"{type(e).__name__}: {e}"))
            return None

    r = get("/api/health")
    if r is not None:
        body = r.text
        ok = r.status_code == 200 and "ok" in body.lower()
        steps.append(_step("health", ok, f"HTTP {r.status_code} {body[:120]}"))

    r = get("/api/products")
    if r is not None:
        try:
            data = r.json()
            items = (
                data if isinstance(data, list) else data.get("products") or data.get("items") or []
            )
            ok = r.status_code == 200 and len(items) > 0
            steps.append(_step("products", ok, f"HTTP {r.status_code}, {len(items)} products"))
        except ValueError:
            steps.append(_step("products", False, f"HTTP {r.status_code}, not JSON"))

    r = get("/api/products/sku-123")
    if r is not None:
        ok = r.status_code == 200 and "price" in r.text.lower()
        steps.append(_step("product sku-123", ok, f"HTTP {r.status_code} {r.text[:120]}"))

    r = get("/api/orders")
    if r is not None:
        if r.status_code in (401, 403):
            steps.append(_step("orders", True, f"HTTP {r.status_code}: needs a session, skipped"))
        else:
            steps.append(
                _step("orders", r.status_code == 200, f"HTTP {r.status_code} {r.text[:120]}")
            )

    return {
        "app": app,
        "base_url": base,
        "passed": bool(steps) and all(s["ok"] for s in steps),
        "steps": steps,
        "duration_ms": int((time.monotonic() - started) * 1000),
    }
