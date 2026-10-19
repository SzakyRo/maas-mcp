"""Tests for the per-request logging middleware."""

from __future__ import annotations

from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from maasmcp.request_log import request_log_middleware


def _app() -> Starlette:
    async def ok(request: Request) -> PlainTextResponse:
        return PlainTextResponse("ok")

    async def post_ok(request: Request) -> PlainTextResponse:
        return PlainTextResponse("ok")

    return Starlette(
        routes=[Route("/mcp", ok), Route("/call", post_ok, methods=["POST"])],
        middleware=[request_log_middleware()],
    )


def test_request_log_emits_structlog_event(monkeypatch) -> None:
    captured: list[dict[str, object]] = []

    def fake_info(event: str, **kwargs: object) -> None:
        if event == "http_request":
            captured.append({"event": event, **kwargs})

    import maasmcp.request_log as module

    monkeypatch.setattr(module.log, "info", fake_info)

    client = TestClient(_app())
    response = client.post(
        "/call",
        headers={"Authorization": "Bearer abcdef0123456789"},
        json={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": "machines_list"},
            "id": 1,
        },
    )
    assert response.status_code == 200

    assert len(captured) == 1, captured
    record = captured[0]
    assert record["event"] == "http_request"
    assert record["bearer_prefix"] == "abcdef"
    assert record["method"] == "tools/call"
    assert record["tool"] == "machines_list"
    assert record["outcome"] == "200"
    assert isinstance(record["latency_ms"], (int, float))
    assert record["latency_ms"] >= 0
    assert record["path"] == "/call"


def test_request_log_emits_event_for_unauthenticated_request(monkeypatch) -> None:
    captured: list[dict[str, object]] = []

    def fake_info(event: str, **kwargs: object) -> None:
        if event == "http_request":
            captured.append({"event": event, **kwargs})

    import maasmcp.request_log as module

    monkeypatch.setattr(module.log, "info", fake_info)

    client = TestClient(_app())
    response = client.get("/mcp")
    assert response.status_code == 200
    assert len(captured) == 1
    assert captured[0]["bearer_prefix"] == "anon"
    assert captured[0]["outcome"] == "200"


def test_oversized_body_streams_without_full_buffering() -> None:
    """Regression: bodies larger than the replay cap must reach the app
    intact (streamed past the buffer) rather than being fully resident.

    TestClient coalesces request bodies into a single ``more_body=False``
    chunk no matter how they're posted, so the overflow path can only be
    exercised by scripting the ASGI receive channel directly.
    """
    import asyncio

    import maasmcp.request_log as module

    async def run() -> None:
        original = module._MAX_BUFFERED_BYTES
        module._MAX_BUFFERED_BYTES = 1024
        try:
            # 3 chunks of 1024 bytes: chunk 1 fills the cap, chunks 2-3 must
            # stream through the original channel via the replay wrapper.
            script = iter(
                [
                    {"type": "http.request", "body": b"a" * 1024, "more_body": True},
                    {"type": "http.request", "body": b"b" * 1024, "more_body": True},
                    {"type": "http.request", "body": b"c" * 1024, "more_body": False},
                ]
            )

            async def original_receive() -> dict[str, Any]:
                return next(script)

            buffered, captured, complete, overflow = await module._drain_body(original_receive)
            assert not complete
            assert overflow
            assert sum(len(m["body"]) for m in buffered) == 1024  # only one chunk buffered
            assert len(captured) == 1024

            # The app replays the buffered chunk, then streams the rest live.
            # Total body must be intact and in order; stop at more_body=False.
            replay = module._make_replaying_receive(buffered, original_receive, overflow=overflow)
            got = bytearray()
            while True:
                msg = await replay()
                if msg["type"] == "http.request":
                    got.extend(msg["body"])
                    if not msg.get("more_body"):
                        break
                elif msg["type"] == "http.disconnect":
                    break
            assert bytes(got) == b"a" * 1024 + b"b" * 1024 + b"c" * 1024
        finally:
            module._MAX_BUFFERED_BYTES = original

    asyncio.run(run())


def test_small_body_multi_chunk_no_overflow() -> None:
    """Many small chunks under the cap buffer fully; completion is signalled
    by more_body=False, and no bytes are dropped or duplicated."""
    import asyncio

    import maasmcp.request_log as module

    async def run() -> None:
        script = iter(
            [{"type": "http.request", "body": b"x", "more_body": True}] * 4
            + [{"type": "http.request", "body": b"y", "more_body": False}]
        )

        async def original_receive() -> dict[str, Any]:
            return next(script)

        buffered, captured, complete, overflow = await module._drain_body(original_receive)
        assert complete and not overflow
        replay = module._make_replaying_receive(buffered, original_receive, overflow=overflow)
        got = bytearray()
        while True:
            msg = await replay()
            if msg["type"] == "http.disconnect":
                break
            got.extend(msg["body"])
        assert bytes(got) == b"xxxxy"
        assert bytes(captured) == b"xxxxy"

    asyncio.run(run())
