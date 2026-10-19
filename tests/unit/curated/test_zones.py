"""zone tools: list/read/create/update/delete + confirm gates."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from maasmcp.config import MaasmcpConfig
from maasmcp.curated.zone_delete import ZoneDeleteTool
from maasmcp.curated.zone_read import ZoneReadTool
from maasmcp.curated.zone_update import ZoneUpdateTool
from maasmcp.curated.zones_create import ZonesCreateTool
from maasmcp.curated.zones_list import ZonesListTool
from maasmcp.maas.client import MaasClient

pytestmark = pytest.mark.asyncio


def _client(monkeypatch: pytest.MonkeyPatch) -> MaasClient:
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    return maas_client


async def test_zones_list_happy(monkeypatch):
    maas_client = _client(monkeypatch)
    with respx.mock(base_url=maas_client.base_url) as mock:
        route = mock.get("/api/2.0/zones/").mock(
            return_value=Response(200, json=[{"id": 1, "name": "default"}])
        )
        async with maas_client:
            result = await ZonesListTool().run(maas_client)
    assert route.called
    assert result == [{"id": 1, "name": "default"}]
    assert "paginate" not in route.calls[0].request.url.params


async def test_zone_read_happy_and_url_quoting(monkeypatch):
    maas_client = _client(monkeypatch)
    with respx.mock(base_url=maas_client.base_url) as mock:
        route = mock.get("/api/2.0/zones/east%20dc/").mock(
            return_value=Response(200, json={"id": 2, "name": "east dc"})
        )
        async with maas_client:
            result = await ZoneReadTool().run(maas_client, name="east dc")
    assert route.called
    assert result["name"] == "east dc"


async def test_zone_read_non_dict_raises(monkeypatch):
    maas_client = _client(monkeypatch)
    with respx.mock(base_url=maas_client.base_url) as mock:
        mock.get("/api/2.0/zones/x/").mock(return_value=Response(200, json=["bad"]))
        async with maas_client:
            with pytest.raises(ValueError, match="non-dict"):
                await ZoneReadTool().run(maas_client, name="x")


async def test_zones_create_happy(monkeypatch):
    maas_client = _client(monkeypatch)
    with respx.mock(base_url=maas_client.base_url) as mock:
        route = mock.post("/api/2.0/zones/").mock(
            return_value=Response(200, json={"id": 3, "name": "edge"})
        )
        async with maas_client:
            result = await ZonesCreateTool().run(
                maas_client, name="edge", description="edge dc", confirm=True
            )
    assert route.called
    assert result == {"id": 3, "name": "edge"}
    body = route.calls.last.request.content.decode(errors="replace")
    assert 'name="name"' in body and 'name="description"' in body


async def test_zones_create_requires_confirm_and_name(monkeypatch):
    maas_client = _client(monkeypatch)
    with respx.mock(base_url=maas_client.base_url) as mock:
        async with maas_client:
            with pytest.raises(ValueError, match="confirm=True"):
                await ZonesCreateTool().run(maas_client, name="edge", confirm=False)
            with pytest.raises(ValueError, match="non-empty name"):
                await ZonesCreateTool().run(maas_client, name="  ", confirm=True)
    assert not mock.calls


async def test_zone_update_rename_and_description(monkeypatch):
    maas_client = _client(monkeypatch)
    with respx.mock(base_url=maas_client.base_url) as mock:
        route = mock.put("/api/2.0/zones/edge/").mock(
            return_value=Response(200, json={"id": 3, "name": "edge-2"})
        )
        async with maas_client:
            result = await ZoneUpdateTool().run(
                maas_client, name="edge", new_name="edge-2", confirm=True
            )
    assert route.called
    assert result["name"] == "edge-2"
    body = route.calls.last.request.content.decode(errors="replace")
    assert 'name="name"' in body and "edge-2" in body


async def test_zone_update_requires_a_change_and_confirm(monkeypatch):
    maas_client = _client(monkeypatch)
    with respx.mock(base_url=maas_client.base_url) as mock:
        async with maas_client:
            with pytest.raises(ValueError, match="requires new_name or description"):
                await ZoneUpdateTool().run(maas_client, name="edge", confirm=True)
            with pytest.raises(ValueError, match="confirm=True"):
                await ZoneUpdateTool().run(maas_client, name="edge", description="d")
    assert not mock.calls


async def test_zone_delete_happy_and_gate(monkeypatch):
    maas_client = _client(monkeypatch)
    with respx.mock(base_url=maas_client.base_url) as mock:
        route = mock.delete("/api/2.0/zones/edge/").mock(return_value=Response(204))
        async with maas_client:
            await ZoneDeleteTool().run(maas_client, name="edge", confirm=True)
    assert route.called
    with respx.mock(base_url=maas_client.base_url) as mock2:
        async with maas_client:
            with pytest.raises(ValueError, match="confirm=True"):
                await ZoneDeleteTool().run(maas_client, name="edge", confirm=False)
    assert not mock2.calls
