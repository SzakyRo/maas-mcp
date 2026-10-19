"""Tests for the bearer-token auth middleware."""

from __future__ import annotations

import hmac

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from maasmcp.auth import require_bearer


def _app(expected: str) -> Starlette:
    async def ok(request: Request) -> PlainTextResponse:
        return PlainTextResponse("ok")

    async def health(request: Request) -> PlainTextResponse:
        return PlainTextResponse("healthy")

    return Starlette(
        routes=[
            Route("/healthz", health),
            Route("/mcp", ok),
        ],
        middleware=[require_bearer(expected)],
    )


def test_correct_token_is_allowed() -> None:
    client = TestClient(_app("secret"))
    response = client.get("/mcp", headers={"Authorization": "Bearer secret"})
    assert response.status_code == 200
    assert response.text == "ok"


def test_missing_token_is_401() -> None:
    client = TestClient(_app("secret"))
    response = client.get("/mcp")
    assert response.status_code == 401
    assert response.text == ""


def test_wrong_token_is_401() -> None:
    client = TestClient(_app("secret"))
    response = client.get("/mcp", headers={"Authorization": "Bearer nope"})
    assert response.status_code == 401
    assert response.text == ""


def test_malformed_header_is_401() -> None:
    client = TestClient(_app("secret"))
    response = client.get("/mcp", headers={"Authorization": "secret"})  # no Bearer prefix
    assert response.status_code == 401


def test_healthz_is_exempt() -> None:
    client = TestClient(_app("secret"))
    response = client.get("/healthz")
    assert response.status_code == 200


def test_comparison_uses_compare_digest(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sanity: the middleware should compare tokens in constant time."""
    calls: list[bool] = []
    real = hmac.compare_digest

    def spy(a: str, b: str) -> bool:
        out = real(a, b)
        calls.append(out)
        return out

    monkeypatch.setattr("maasmcp.auth.hmac.compare_digest", spy)
    client = TestClient(_app("secret"))
    client.get("/mcp", headers={"Authorization": "Bearer nope"})
    assert calls == [False]


def test_empty_expected_token_never_authenticates() -> None:
    """Regression: compare_digest("", "") is True — an empty configured token
    must NOT let headerless requests through (e.g. docker-compose substituting
    an unset env var as an empty string)."""
    client = TestClient(_app(""))
    assert client.get("/mcp").status_code == 401
    assert client.get("/mcp", headers={"Authorization": "Bearer "}).status_code == 401
