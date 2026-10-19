"""Tests for MaasClient: auth, retry, OAuth."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from maasmcp.config import MaasConfig, MaasmcpConfig, ServerConfig
from maasmcp.maas.client import MaasClient
from maasmcp.maas.errors import MAASAuthError, MCPUpstreamError, MCPUpstreamTimeout

FIXTURES = Path(__file__).parent.parent / "fixtures" / "maas" / "responses"


@pytest.fixture(autouse=True)
def _no_retry_delays(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep retry tests fast: zero out the backoff schedule instead of
    sleeping 0.25+1.0+4.0s per multi-attempt test."""
    monkeypatch.setattr("maasmcp.maas.client._RETRY_DELAYS_S", (0.0, 0.0, 0.0))


def _api_key_config(key: str = "test-key") -> MaasConfig:
    return MaasConfig(base_url="https://maas.example.com/MAAS", api_key=key)


@pytest.mark.asyncio
@respx.mock
async def test_get_with_api_key_sends_bearer() -> None:
    route = respx.get("https://maas.example.com/MAAS/api/2.0/machines/").mock(
        return_value=httpx.Response(
            200, json=json.loads((FIXTURES / "machines_list.json").read_text())
        )
    )
    async with MaasClient(_api_key_config()) as client:
        result = await client.get("/api/2.0/machines/")
    assert isinstance(result, list)
    assert result[0]["hostname"] == "node-1"
    sent = route.calls.last.request
    assert sent.headers["authorization"] == "Bearer test-key"


@pytest.mark.asyncio
@respx.mock
async def test_5xx_retries_then_raises() -> None:
    respx.get("https://maas.example.com/MAAS/api/2.0/machines/").mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(503),
            httpx.Response(503),
            httpx.Response(503),
        ]
    )
    async with MaasClient(_api_key_config()) as client:
        with pytest.raises(MCPUpstreamError) as exc:
            await client.get("/api/2.0/machines/")
    assert exc.value.status_code == 503
    # 1 initial + 3 retries = 4 attempts
    assert respx.calls.call_count == 4


@pytest.mark.asyncio
@respx.mock
async def test_deterministic_500_fails_fast_without_retry() -> None:
    """MAAS's bare Django-DoesNotExist 500s (e.g. "PartitionTable matching
    query does not exist") can never succeed on retry — the client must raise
    immediately instead of paying the full backoff schedule."""
    respx.get("https://maas.example.com/MAAS/api/2.0/nodes/abc/blockdevices/1/partitions/").mock(
        return_value=httpx.Response(500, text="PartitionTable matching query does not exist")
    )
    async with MaasClient(_api_key_config()) as client:
        with pytest.raises(MCPUpstreamError) as exc:
            await client.get("/api/2.0/nodes/abc/blockdevices/1/partitions/")
    assert exc.value.status_code == 500
    assert "PartitionTable matching query does not exist" in str(exc.value)
    # No retries: a single attempt only.
    assert respx.calls.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_4xx_passes_through_without_retry() -> None:
    respx.get("https://maas.example.com/MAAS/api/2.0/machines/").mock(
        return_value=httpx.Response(404, json={"__error__": "not found"})
    )
    async with MaasClient(_api_key_config()) as client:
        with pytest.raises(MCPUpstreamError) as exc:
            await client.get("/api/2.0/machines/")
    assert exc.value.status_code == 404
    assert respx.calls.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_2xx_after_one_5xx_succeeds() -> None:
    respx.get("https://maas.example.com/MAAS/api/2.0/machines/").mock(
        side_effect=[httpx.Response(503), httpx.Response(200, json=[])]
    )
    async with MaasClient(_api_key_config()) as client:
        result = await client.get("/api/2.0/machines/")
    assert result == []


@pytest.mark.asyncio
@respx.mock
async def test_timeout_retries_then_raises_timeout() -> None:
    respx.get("https://maas.example.com/MAAS/api/2.0/machines/").mock(
        side_effect=httpx.ConnectTimeout("boom")
    )
    async with MaasClient(_api_key_config()) as client:
        with pytest.raises(MCPUpstreamTimeout):
            await client.get("/api/2.0/machines/")
    assert respx.calls.call_count == 4


@pytest.mark.asyncio
async def test_no_credentials_raises_auth_error() -> None:
    cfg = MaasConfig(base_url="https://maas.example.com/MAAS")
    with pytest.raises(MAASAuthError):
        async with MaasClient(cfg):
            pass


@pytest.mark.asyncio
@respx.mock
async def test_oauth_signs_request_with_authorization_header() -> None:
    cfg = MaasConfig(
        base_url="https://maas.example.com/MAAS",
        consumer_key="ck",
        consumer_secret="cs",
        token_key="tk",
        token_secret="ts",
    )
    route = respx.get("https://maas.example.com/MAAS/api/2.0/machines/").mock(
        return_value=httpx.Response(200, json=[])
    )
    async with MaasClient(cfg) as client:
        await client.get("/api/2.0/machines/")
    sent = route.calls.last.request
    auth_header = sent.headers["authorization"]
    assert auth_header.startswith("OAuth ")
    assert 'oauth_consumer_key="ck"' in auth_header
    assert 'oauth_token="tk"' in auth_header
    # PLAINTEXT signature is consumer_secret&token_secret, per MAAS docs.
    assert 'oauth_signature_method="PLAINTEXT"' in auth_header
    assert 'oauth_version="1.0"' in auth_header
    assert 'oauth_signature="cs%26ts"' in auth_header


@pytest.mark.asyncio
@respx.mock
async def test_oauth_with_empty_consumer_secret_signs_with_amp_token() -> None:
    """Triple-key MAAS API keys have empty consumer_secret.

    The PLAINTEXT signature becomes ``&<token_secret>`` (URL-encoded as
    ``%26<token_secret>`` in the header value).
    """
    cfg = MaasConfig(
        base_url="https://maas.example.com/MAAS",
        consumer_key="ck",
        consumer_secret="",
        token_key="tk",
        token_secret="ts",
    )
    route = respx.get("https://maas.example.com/MAAS/api/2.0/machines/").mock(
        return_value=httpx.Response(200, json=[])
    )
    async with MaasClient(cfg) as client:
        await client.get("/api/2.0/machines/")
    sent = route.calls.last.request
    auth_header = sent.headers["authorization"]
    assert 'oauth_signature_method="PLAINTEXT"' in auth_header
    assert 'oauth_signature="%26ts"' in auth_header


@pytest.mark.asyncio
async def test_both_auth_modes_raises() -> None:
    """Supplying both api_key and full oauth credentials is a config error."""
    cfg = MaasConfig(
        base_url="https://maas.example.com/MAAS",
        api_key="k",
        consumer_key="ck",
        consumer_secret="cs",
        token_key="tk",
        token_secret="ts",
    )
    with pytest.raises(MAASAuthError):
        async with MaasClient(cfg):
            pass


@pytest.mark.asyncio
@respx.mock
async def test_429_passes_through_without_retry() -> None:
    """429 (rate-limited) is a client-side 4xx — no retry, raise immediately."""
    respx.get("https://maas.example.com/MAAS/api/2.0/machines/").mock(
        return_value=httpx.Response(429, json={"__error__": "rate limited"})
    )
    async with MaasClient(_api_key_config()) as client:
        with pytest.raises(MCPUpstreamError) as exc:
            await client.get("/api/2.0/machines/")
    assert exc.value.status_code == 429
    assert respx.calls.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_post_sends_multipart_form_data() -> None:
    """POST bodies must be multipart/form-data with text parts (per MAAS API)."""
    route = respx.post("https://maas.example.com/MAAS/api/2.0/machines/op-allocate/").mock(
        return_value=httpx.Response(200, json={"system_id": "abc"})
    )
    async with MaasClient(_api_key_config()) as client:
        await client.post(
            "/api/2.0/machines/op-allocate/",
            json={"system_id": "abc", "erase": True},
        )
    sent = route.calls.last.request
    ctype = sent.headers.get("content-type", "")
    assert ctype.startswith("multipart/form-data"), ctype
    body = sent.read().decode()
    # Each key becomes a separate text part; booleans render as 'true'/'false'.
    assert 'name="system_id"' in body
    assert "abc" in body
    assert 'name="erase"' in body
    assert "true" in body  # not Python's 'True'


@pytest.mark.asyncio
@respx.mock
async def test_4xx_error_does_not_leak_body() -> None:
    """Upstream error message must not echo response.text (may contain PII)."""
    respx.get("https://maas.example.com/MAAS/api/2.0/machines/").mock(
        return_value=httpx.Response(
            400,
            json={"hostname-with-secret": "leak-hostname-x"},
        )
    )
    async with MaasClient(_api_key_config()) as client:
        with pytest.raises(MCPUpstreamError) as exc:
            await client.get("/api/2.0/machines/")
    assert "leak-hostname-x" not in str(exc.value)
    assert "hostname-with-secret" not in str(exc.value)


@pytest.mark.asyncio
@respx.mock
async def test_transport_error_retries_then_raises_unreachable() -> None:
    """ConnectError is a TransportError but not a timeout — retries apply,
    but the final error must name the real failure, not 'timeout'."""
    respx.get("https://maas.example.com/MAAS/api/2.0/machines/").mock(
        side_effect=httpx.ConnectError("boom")
    )
    async with MaasClient(_api_key_config()) as client:
        with pytest.raises(MCPUpstreamError) as exc_info:
            await client.get("/api/2.0/machines/")
    assert exc_info.value.status_code == 0
    assert isinstance(exc_info.value.__cause__, httpx.ConnectError)
    assert respx.calls.call_count == 4


@pytest.mark.asyncio
@respx.mock
async def test_paginated_get_false_returns_single_page() -> None:
    route = respx.get("https://maas.example.com/MAAS/api/2.0/machines/").mock(
        return_value=httpx.Response(200, json=[{"system_id": "a"}, {"system_id": "b"}])
    )
    async with MaasClient(_api_key_config()) as client:
        result = await client.paginated_get("/api/2.0/machines/", paginate=False)
    assert result == [{"system_id": "a"}, {"system_id": "b"}]
    assert route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_paginated_get_true_aggregates_pages() -> None:
    route = respx.get("https://maas.example.com/MAAS/api/2.0/machines/").mock(
        side_effect=[
            httpx.Response(200, json=[{"id": i} for i in range(200)]),
            httpx.Response(200, json=[{"id": i} for i in range(200, 350)]),
        ]
    )
    async with MaasClient(_api_key_config()) as client:
        result = await client.paginated_get("/api/2.0/machines/", paginate=True)
    assert isinstance(result, list)
    assert len(result) == 350
    assert route.call_count == 2
    # Pin offset/limit progression: page 2 must request offset=200.
    assert route.calls[0].request.url.params["offset"] == "0"
    assert route.calls[1].request.url.params["offset"] == "200"


@pytest.mark.asyncio
@respx.mock
async def test_paginated_get_caps_at_max_items() -> None:
    # Configured cap of 50; MAAS returns 200 items per page.
    cfg = MaasmcpConfig(
        maas=MaasConfig(base_url="https://maas.example.com/MAAS", api_key="k"),
        server=ServerConfig(bearer_token="test-token-1234567", max_paginated_items=50),
    )
    respx.get("https://maas.example.com/MAAS/api/2.0/machines/").mock(
        side_effect=[
            httpx.Response(200, json=[{"id": i} for i in range(50)]),
            httpx.Response(200, json=[{"id": i} for i in range(50, 100)]),
        ]
    )
    async with MaasClient(cfg) as client:
        assert client.max_paginated_items == 50
        result = await client.paginated_get("/api/2.0/machines/", paginate=True)
    assert isinstance(result, list)
    assert len(result) == 50
    # Should not have made the second request once cap was reached.
    assert respx.calls.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_paginated_get_falls_back_when_endpoint_rejects_pagination() -> None:
    """Regression for live MAAS: /machines/ on releases without collection
    pagination answers 400 {"limit": ["No such constraint."]}. The first
    page's 400 must trigger one un-paginated retry that returns the full
    list (verified against MAAS at 10.72.91.100, 2026-08-30)."""
    full_list = [{"system_id": c} for c in "abc"]
    route = respx.get("https://maas.example.com/MAAS/api/2.0/machines/").mock(
        side_effect=[
            httpx.Response(
                400,
                json={"limit": ["No such constraint."], "offset": ["No such constraint."]},
            ),
            httpx.Response(200, json=full_list),
        ]
    )
    async with MaasClient(_api_key_config()) as client:
        result = await client.paginated_get("/api/2.0/machines/", paginate=True)
    assert result == full_list
    assert route.call_count == 2
    # The fallback request must carry no pagination params at all.
    assert "limit" not in route.calls[1].request.url.params
    assert "offset" not in route.calls[1].request.url.params


@pytest.mark.asyncio
@respx.mock
async def test_paginated_get_fallback_failure_surfaces_error() -> None:
    """If the un-paginated retry also 400s, the caller's other params were
    bad — the error must surface, not be swallowed by the fallback."""
    respx.get("https://maas.example.com/MAAS/api/2.0/machines/").mock(
        return_value=httpx.Response(400, json={"hostname": ["Unknown constraint."]})
    )
    async with MaasClient(_api_key_config()) as client:
        with pytest.raises(MCPUpstreamError, match="400"):
            await client.paginated_get(
                "/api/2.0/machines/", params={"hostname": "nope"}, paginate=True
            )


@pytest.mark.asyncio
@respx.mock
async def test_paginated_get_400_after_first_page_propagates() -> None:
    """The fallback is only for the FIRST page: a 400 mid-walk means
    something else is wrong and must not silently degrade to page 1."""
    respx.get("https://maas.example.com/MAAS/api/2.0/machines/").mock(
        side_effect=[
            httpx.Response(200, json=[{"id": i} for i in range(200)]),
            httpx.Response(400, json={"offset": ["Invalid."]}),
        ]
    )
    async with MaasClient(_api_key_config()) as client:
        with pytest.raises(MCPUpstreamError, match="400"):
            await client.paginated_get("/api/2.0/machines/", paginate=True)


@pytest.mark.asyncio
@respx.mock
async def test_post_5xx_is_not_retried() -> None:
    """Writes are not replayed: a POST whose request reached MAAS must not be
    re-sent after a 5xx, or duplicate resources would be created."""
    route = respx.post("https://maas.example.com/MAAS/api/2.0/machines/").mock(
        return_value=httpx.Response(503)
    )
    async with MaasClient(_api_key_config()) as client:
        with pytest.raises(MCPUpstreamError):
            await client.post("/api/2.0/machines/", json={"hostname": "x"})
    assert route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_post_transport_error_is_not_retried() -> None:
    route = respx.post("https://maas.example.com/MAAS/api/2.0/machines/").mock(
        side_effect=httpx.ConnectError("boom")
    )
    async with MaasClient(_api_key_config()) as client:
        with pytest.raises(MCPUpstreamError) as exc_info:
            await client.post("/api/2.0/machines/", json={"hostname": "x"})
    assert exc_info.value.status_code == 0
    assert route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_3xx_treated_as_error_not_result() -> None:
    """httpx doesn't follow redirects here; a 3xx must not parse as success."""
    respx.get("https://maas.example.com/MAAS/api/2.0/machines/").mock(
        return_value=httpx.Response(302, headers={"location": "/MAAS/accounts/login/"})
    )
    async with MaasClient(_api_key_config()) as client:
        with pytest.raises(MCPUpstreamError):
            await client.get("/api/2.0/machines/")


@pytest.mark.asyncio
@respx.mock
async def test_malformed_json_raises_upstream_error() -> None:
    respx.get("https://maas.example.com/MAAS/api/2.0/machines/").mock(
        return_value=httpx.Response(
            200, content=b"not-json{", headers={"content-type": "application/json"}
        )
    )
    async with MaasClient(_api_key_config()) as client:
        with pytest.raises(MCPUpstreamError, match="malformed JSON"):
            await client.get("/api/2.0/machines/")


@pytest.mark.asyncio
@respx.mock
async def test_error_url_strips_query_string() -> None:
    """4xx/5xx error URLs must not carry the query string (user input)."""
    respx.get("https://maas.example.com/MAAS/api/2.0/machines/").mock(
        return_value=httpx.Response(404)
    )
    async with MaasClient(_api_key_config()) as client:
        with pytest.raises(MCPUpstreamError) as exc_info:
            await client.get("/api/2.0/machines/", params={"hostname": "secret-host"})
    assert "secret-host" not in exc_info.value.url
    assert "?" not in exc_info.value.url


@pytest.mark.asyncio
@respx.mock
async def test_paginated_get_stops_on_oversized_page() -> None:
    """Endpoint ignoring BOTH limit and offset echoes the same page for every
    offset — detect by content and stop without duplicating items."""
    route = respx.get("https://maas.example.com/MAAS/api/2.0/machines/").mock(
        return_value=httpx.Response(200, json=[{"id": i} for i in range(500)])
    )
    async with MaasClient(_api_key_config()) as client:
        result = await client.paginated_get("/api/2.0/machines/", paginate=True)
    assert isinstance(result, list)
    assert len(result) == 500
    # One real fetch + one echo that is detected and discarded.
    assert route.call_count == 2


@pytest.mark.asyncio
@respx.mock
async def test_paginated_get_collects_oversized_pages_when_offset_honored() -> None:
    """Endpoint ignoring `limit` but honoring `offset` (fixed 500-item server
    pages): every item must still be collected — the dedup guard must only
    fire on an actual echo."""
    items = [{"id": i} for i in range(1200)]

    def handler(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params.get("offset", "0"))
        return httpx.Response(200, json=items[offset : offset + 500])

    respx.get("https://maas.example.com/MAAS/api/2.0/machines/").mock(side_effect=handler)
    cfg = MaasmcpConfig(
        maas=MaasConfig(base_url="https://maas.example.com/MAAS", api_key="k"),
        server=ServerConfig(bearer_token="test-token-1234567", max_paginated_items=1500),
    )
    async with MaasClient(cfg) as client:
        result = await client.paginated_get("/api/2.0/machines/", paginate=True)
    assert isinstance(result, list)
    assert len(result) == 1200
    assert [m["id"] for m in result] == list(range(1200))  # no duplicates


# --- auth/session retry and actionable error detail tests ------------------


@pytest.mark.asyncio
@respx.mock
async def test_post_401_is_retried_and_eventually_raises() -> None:
    """Auth/session failures are safe to replay: MAAS rejected the request
    before it reached the application, so no duplicate resource is created."""
    route = respx.post("https://maas.example.com/MAAS/api/2.0/machines/").mock(
        return_value=httpx.Response(401, text="Unauthorized")
    )
    async with MaasClient(_api_key_config()) as client:
        with pytest.raises(MCPUpstreamError) as exc:
            await client.post("/api/2.0/machines/", json={"hostname": "x"})
    assert exc.value.status_code == 401
    assert route.call_count == 4


@pytest.mark.asyncio
@respx.mock
async def test_put_403_session_expired_is_retried() -> None:
    route = respx.put("https://maas.example.com/MAAS/api/2.0/machines/abc/").mock(
        side_effect=[
            httpx.Response(403, text="CSRF session has expired"),
            httpx.Response(200, json={"system_id": "abc"}),
        ]
    )
    async with MaasClient(_api_key_config()) as client:
        result = await client.put("/api/2.0/machines/abc/", json={"hostname": "x"})
    assert result == {"system_id": "abc"}
    assert route.call_count == 2


@pytest.mark.asyncio
@respx.mock
async def test_403_without_session_text_is_not_retried() -> None:
    route = respx.get("https://maas.example.com/MAAS/api/2.0/machines/").mock(
        return_value=httpx.Response(403, text="Permission denied")
    )
    async with MaasClient(_api_key_config()) as client:
        with pytest.raises(MCPUpstreamError) as exc:
            await client.get("/api/2.0/machines/")
    assert exc.value.status_code == 403
    assert route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_get_401_eventually_raises_after_retries() -> None:
    route = respx.get("https://maas.example.com/MAAS/api/2.0/machines/").mock(
        return_value=httpx.Response(401, text="Unauthorized")
    )
    async with MaasClient(_api_key_config()) as client:
        with pytest.raises(MCPUpstreamError) as exc:
            await client.get("/api/2.0/machines/")
    assert exc.value.status_code == 401
    assert route.call_count == 4


@pytest.mark.asyncio
@respx.mock
async def test_post_non_auth_4xx_is_not_retried() -> None:
    route = respx.post("https://maas.example.com/MAAS/api/2.0/machines/").mock(
        return_value=httpx.Response(400, json={"__error__": "bad request"})
    )
    async with MaasClient(_api_key_config()) as client:
        with pytest.raises(MCPUpstreamError) as exc:
            await client.post("/api/2.0/machines/", json={"hostname": "x"})
    assert exc.value.status_code == 400
    assert route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_structured_json_error_is_surfaced_in_detail() -> None:
    respx.get("https://maas.example.com/MAAS/api/2.0/machines/").mock(
        return_value=httpx.Response(400, json={"__error__": "hostname already exists"})
    )
    async with MaasClient(_api_key_config()) as client:
        with pytest.raises(MCPUpstreamError) as exc:
            await client.get("/api/2.0/machines/")
    assert exc.value.detail == "hostname already exists"


@pytest.mark.asyncio
@respx.mock
async def test_field_level_json_error_is_surfaced_in_detail() -> None:
    respx.get("https://maas.example.com/MAAS/api/2.0/machines/").mock(
        return_value=httpx.Response(
            400, json={"hostname": ["Invalid characters"], "domain": ["Required"]}
        )
    )
    async with MaasClient(_api_key_config()) as client:
        with pytest.raises(MCPUpstreamError) as exc:
            await client.get("/api/2.0/machines/")
    assert "hostname: Invalid characters" in str(exc.value)
    assert "domain: Required" in str(exc.value)


@pytest.mark.asyncio
@respx.mock
async def test_plain_text_error_is_surfaced_and_truncated() -> None:
    body = "MAAS error: " + "x" * 500
    respx.get("https://maas.example.com/MAAS/api/2.0/machines/").mock(
        return_value=httpx.Response(500, text=body)
    )
    async with MaasClient(_api_key_config()) as client:
        with pytest.raises(MCPUpstreamError) as exc:
            await client.get("/api/2.0/machines/")
    assert exc.value.detail is not None
    assert len(exc.value.detail) <= 250
    assert "MAAS error" in exc.value.detail


@pytest.mark.asyncio
@respx.mock
async def test_html_error_is_stripped_and_surfaced() -> None:
    html = "<html><body><h1>Internal Server Error</h1><p>Database is down</p></body></html>"
    respx.get("https://maas.example.com/MAAS/api/2.0/machines/").mock(
        return_value=httpx.Response(500, text=html, headers={"content-type": "text/html"})
    )
    async with MaasClient(_api_key_config()) as client:
        with pytest.raises(MCPUpstreamError) as exc:
            await client.get("/api/2.0/machines/")
    assert exc.value.detail is not None
    assert "Database is down" in exc.value.detail
    assert "<html>" not in exc.value.detail


@pytest.mark.asyncio
@respx.mock
async def test_unknown_json_error_does_not_leak_body() -> None:
    """Arbitrary JSON payloads may contain PII; only recognized keys are echoed."""
    respx.get("https://maas.example.com/MAAS/api/2.0/machines/").mock(
        return_value=httpx.Response(400, json={"hostname-with-secret": "leak-hostname-x"})
    )
    async with MaasClient(_api_key_config()) as client:
        with pytest.raises(MCPUpstreamError) as exc:
            await client.get("/api/2.0/machines/")
    assert exc.value.detail is None
    assert "leak-hostname-x" not in str(exc.value)
    assert "hostname-with-secret" not in str(exc.value)


@pytest.mark.asyncio
@respx.mock
async def test_field_level_json_error_ignores_unsafe_field_names() -> None:
    """Only safe, non-credential field names are echoed from validation envelopes."""
    respx.get("https://maas.example.com/MAAS/api/2.0/machines/").mock(
        return_value=httpx.Response(
            400,
            json={
                "hostname": ["Invalid characters"],
                "api_key": ["too short"],
                "hostname-with-secret": ["leak"],
            },
        )
    )
    async with MaasClient(_api_key_config()) as client:
        with pytest.raises(MCPUpstreamError) as exc:
            await client.get("/api/2.0/machines/")
    detail = exc.value.detail
    assert detail is not None
    assert "hostname: Invalid characters" in detail
    assert "api_key" not in detail
    assert "too short" not in detail
    assert "leak" not in detail


@pytest.mark.asyncio
@respx.mock
async def test_403_invalid_token_format_is_not_retried() -> None:
    """Generic 'token' or 'session' substrings must not trigger write retries."""
    route = respx.post("https://maas.example.com/MAAS/api/2.0/machines/").mock(
        return_value=httpx.Response(403, text="Invalid token format")
    )
    async with MaasClient(_api_key_config()) as client:
        with pytest.raises(MCPUpstreamError) as exc:
            await client.post("/api/2.0/machines/", json={"hostname": "x"})
    assert exc.value.status_code == 403
    assert route.call_count == 1
