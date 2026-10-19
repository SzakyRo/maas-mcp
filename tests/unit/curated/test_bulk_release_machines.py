"""bulk_release_machines: per-machine op-release fan-out."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from maasmcp.config import MaasmcpConfig
from maasmcp.curated.bulk_release_machines import BulkReleaseMachinesTool
from maasmcp.maas.client import MaasClient


@pytest.mark.asyncio
async def test_happy_path_one_post_per_host(maas_client: MaasClient) -> None:
    """MAAS's collection op-release drops erase/force options, so the tool
    fans out one per-machine op-release call per host."""
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        route_abc = mock.post("/api/2.0/machines/abc/op-release").mock(
            return_value=Response(200, json={"system_id": "abc"})
        )
        route_def = mock.post("/api/2.0/machines/def/op-release").mock(
            return_value=Response(200, json={"system_id": "def"})
        )
        async with maas_client:
            tool = BulkReleaseMachinesTool()
            result = await tool.run(
                maas_client,
                system_ids=["abc", "def"],
                erase=True,
                confirm=True,
            )
    assert route_abc.call_count == 1
    assert route_def.call_count == 1
    assert result == [
        {"system_id": "abc", "status": "ok", "result": {"system_id": "abc"}},
        {"system_id": "def", "status": "ok", "result": {"system_id": "def"}},
    ]


@pytest.mark.asyncio
async def test_partial_failure_returns_per_item_status(maas_client: MaasClient) -> None:
    """One host 409s, the other succeeds: list contains ok and error entries."""
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        mock.post("/api/2.0/machines/abc/op-release").mock(
            return_value=Response(200, json={"system_id": "abc"})
        )
        mock.post("/api/2.0/machines/def/op-release").mock(
            return_value=Response(409, text="machine is in DEPLOYING")
        )
        async with maas_client:
            tool = BulkReleaseMachinesTool()
            result = await tool.run(maas_client, system_ids=["abc", "def"], confirm=True)
    assert result[0]["status"] == "ok"
    assert result[1]["status"] == "error"
    assert "409" in result[1]["error"]


@pytest.mark.asyncio
async def test_http_error_marks_all_items_error(maas_client: MaasClient) -> None:
    """409s from MAAS on both hosts: every item is errored with the reason."""
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        mock.post("/api/2.0/machines/abc/op-release").mock(
            return_value=Response(409, text="state conflict")
        )
        mock.post("/api/2.0/machines/def/op-release").mock(
            return_value=Response(409, text="state conflict")
        )
        async with maas_client:
            tool = BulkReleaseMachinesTool()
            result = await tool.run(maas_client, system_ids=["abc", "def"], confirm=True)
    assert len(result) == 2
    assert all(item["status"] == "error" for item in result)
    # Commit 5ad4a1a strips response bodies from MCPUpstreamError so sensitive
    # MAAS data doesn't leak; assert on the status code ("upstream 409") instead.
    assert "409" in result[0]["error"]


@pytest.mark.asyncio
async def test_empty_system_ids_returns_empty_list(maas_client: MaasClient) -> None:
    """No MAAS call when system_ids is empty (and confirm is irrelevant here)."""
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        tool = BulkReleaseMachinesTool()
        result = await tool.run(maas_client, system_ids=[])
    assert result == []
    assert not mock.calls


@pytest.mark.asyncio
async def test_requires_confirm(maas_client: MaasClient) -> None:
    """Gate runs before any MAAS call. confirm=False (default) must reject."""
    with respx.mock(base_url=maas_client.base_url, assert_all_called=False) as mock:  # type: ignore[attr-defined]
        route = mock.post("/api/2.0/machines/abc/op-release").mock(
            return_value=Response(200, json=True)
        )
        async with maas_client:
            with pytest.raises(ValueError, match="confirm=True"):
                await BulkReleaseMachinesTool().run(maas_client, system_ids=["abc", "def"])
    # Gate runs before any MAAS call — the mocked endpoint must NOT be hit.
    assert route.call_count == 0


@pytest.mark.asyncio
async def test_erase_flags_propagate_as_data_fields(maas_client: MaasClient) -> None:
    """erase/secure_erase/quick_erase/force become multipart data fields on
    the per-machine op-release call."""
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        route = mock.post("/api/2.0/machines/abc/op-release").mock(
            return_value=Response(200, json=True)
        )
        async with maas_client:
            await BulkReleaseMachinesTool().run(
                maas_client,
                system_ids=["abc"],
                comment="decom",
                erase=False,
                secure_erase=True,
                quick_erase=True,
                force=True,
                confirm=True,
            )
    sent = route.calls.last.request
    assert b'name="comment"' in sent.content and b"decom" in sent.content
    assert b'name="erase"' in sent.content and b"false" in sent.content
    assert b'name="secure_erase"' in sent.content
    assert b'name="quick_erase"' in sent.content
    assert b'name="force"' in sent.content


async def test_bulk_release_by_hostnames(monkeypatch) -> None:
    """hostnames list resolves via one fleet fetch; unmatched → error entry."""
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url, assert_all_called=False) as mock:
        mock.get("/api/2.0/machines/").mock(
            return_value=Response(
                200,
                json=[{"system_id": "aa1", "hostname": "node-1"}],
            )
        )
        release_route = mock.post("/api/2.0/machines/aa1/op-release").mock(
            return_value=Response(200, json={"system_id": "aa1"})
        )
        async with maas_client:
            results = await BulkReleaseMachinesTool().run(
                maas_client,
                hostnames=["node-1", "ghost"],
                confirm=True,
            )
    assert release_route.call_count == 1
    # Reordered results come first (matching input order); hostname misses
    # are appended after them.
    assert [r["system_id"] for r in results] == ["aa1", "ghost"]
    by_sid = {r["system_id"]: r for r in results}
    assert by_sid["aa1"]["status"] == "ok"
    assert by_sid["ghost"]["status"] == "error"


async def test_bulk_release_both_none_raises(monkeypatch) -> None:
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    async with maas_client:
        with pytest.raises(ValueError, match="system_ids or hostnames"):
            await BulkReleaseMachinesTool().run(maas_client, confirm=True)


@pytest.mark.asyncio
async def test_invalid_system_id_validates_before_confirm_gate(maas_client: MaasClient) -> None:
    """Validation must fire BEFORE the confirm gate so an invalid explicit
    system_id surfaces the validation error rather than the generic
    confirm-gate rejection (mirrors pre-branch behaviour)."""
    with respx.mock(base_url=maas_client.base_url, assert_all_called=False) as mock:
        route = mock.post("/api/2.0/machines/../op-release").mock(
            return_value=Response(200, json={})
        )
        async with maas_client:
            with pytest.raises(ValueError, match="system_id must be 1-64"):
                await BulkReleaseMachinesTool().run(
                    maas_client, system_ids=["../bad"], confirm=False
                )
    assert route.call_count == 0


@pytest.mark.asyncio
async def test_confirm_message_includes_actual_ids(maas_client: MaasClient) -> None:
    """Gate message lists the actual system_ids (and hostnames), not counts."""
    async with maas_client:
        with pytest.raises(ValueError, match=r"system_ids=\['abc', 'def'\]"):
            await BulkReleaseMachinesTool().run(
                maas_client, system_ids=["abc", "def"], confirm=False
            )
