"""HTTP client for the Platform API. Same JSON a UI would use."""

from __future__ import annotations

import os
from typing import Any

import httpx

DEFAULT_API_URL = "http://localhost:8000"


class ApiError(RuntimeError):
    pass


class ApiClient:
    def __init__(
        self,
        base_url: str | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = (base_url or os.environ.get("PLATFORM_API_URL") or DEFAULT_API_URL).rstrip(
            "/"
        )
        self._client = httpx.Client(base_url=self.base_url, transport=transport, timeout=timeout)

    def _call(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            resp = self._client.request(method, path, **kwargs)
        except httpx.HTTPError as e:
            raise ApiError(f"cannot reach the platform API at {self.base_url}: {e}") from e
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail", resp.text)
            except ValueError:
                detail = resp.text
            raise ApiError(f"{method} {path} -> {resp.status_code}: {detail}")
        return resp.json()

    def catalog(self) -> list[dict[str, Any]]:
        return self._call("GET", "/catalog")

    def catalog_type(self, type_name: str) -> dict[str, Any]:
        return self._call("GET", f"/catalog/{type_name}")

    def create_request(
        self, type_name: str, inputs: dict[str, Any], requested_by: str, environment: str
    ) -> dict[str, Any]:
        return self._call(
            "POST",
            "/requests",
            json={
                "type": type_name,
                "inputs": inputs,
                "requested_by": requested_by,
                "environment": environment,
            },
        )

    def request(self, request_id: str) -> dict[str, Any]:
        return self._call("GET", f"/requests/{request_id}")

    def requests(self, state: str | None = None) -> list[dict[str, Any]]:
        params = {"state": state} if state else {}
        return self._call("GET", "/requests", params=params)

    def audit(self, request_id: str | None = None) -> list[dict[str, Any]]:
        params = {"request": request_id} if request_id else {}
        return self._call("GET", "/audit", params=params)
