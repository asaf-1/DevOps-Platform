"""The platform's HTTP smoke test of a tenant app, against a fake app."""

import json

import httpx

from platform_api.smoke import run_smoke


def fake_app(healthy: bool = True) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/health":
            if not healthy:
                return httpx.Response(503, text="database failed to start")
            return httpx.Response(200, json={"status": "ok"})
        if path == "/api/products":
            return httpx.Response(
                200, json=[{"sku": "sku-123", "price": 10}, {"sku": "sku-9", "price": 3}]
            )
        if path == "/api/products/sku-123":
            return httpx.Response(200, json={"sku": "sku-123", "price": "$10.00"})
        if path == "/api/orders":
            return httpx.Response(401, json={"message": "sign in"})
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_smoke_passes_on_a_healthy_app() -> None:
    result = run_smoke("bank", "http://bank.test", client=fake_app())
    assert result["passed"] is True
    assert [s["name"] for s in result["steps"]] == [
        "health",
        "products",
        "product sku-123",
        "orders",
    ]
    assert all(s["ok"] for s in result["steps"])
    assert "skipped" in result["steps"][-1]["detail"]
    json.dumps(result)  # serialisable for the API


def test_smoke_fails_on_a_broken_health_check() -> None:
    result = run_smoke("bank", "http://bank.test", client=fake_app(healthy=False))
    assert result["passed"] is False
    health = result["steps"][0]
    assert health["name"] == "health" and health["ok"] is False and "503" in health["detail"]


def test_smoke_reports_an_unreachable_app() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    result = run_smoke(
        "bank", "http://bank.test", client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    assert result["passed"] is False
    assert all(not s["ok"] for s in result["steps"])
    assert "ConnectError" in result["steps"][0]["detail"]
