"""acquire_machine: deterministic candidate selection and pre-flight filtering."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from maasmcp.config import MaasmcpConfig
from maasmcp.curated.acquire_machine import AcquireMachineTool
from maasmcp.maas.client import MaasClient


def _client(monkeypatch: pytest.MonkeyPatch) -> MaasClient:
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    return maas_client


@pytest.mark.asyncio
async def test_acquire_picks_lexically_first_system_id(monkeypatch) -> None:
    """Two Ready machines in the same pool: MAAS's listing order is NOT
    guaranteed stable across versions, so acquire_machine MUST sort by
    system_id before picking. Without this, identical inputs against
    different fleet orderings allocate different machines."""
    maas_client = _client(monkeypatch)
    # Fleet returns the candidates in an order that is NOT lexically sorted
    # by system_id — "z" comes before "a". acquire_machine must pick "a".
    fleet = [
        {"system_id": "z", "status_name": "Ready", "hostname": "node-z", "pool": {"name": "p"}},
        {"system_id": "a", "status_name": "Ready", "hostname": "node-a", "pool": {"name": "p"}},
    ]
    with respx.mock(base_url=maas_client.base_url) as mock:
        mock.get("/api/2.0/machines/", params={"limit": "200", "offset": "0"}).mock(
            return_value=Response(200, json=fleet)
        )
        allocate_route = mock.post("/api/2.0/machines/?op=allocate").mock(
            return_value=Response(200, json={"system_id": "a"})
        )
        async with maas_client:
            result = await AcquireMachineTool().run(maas_client, pool="p", confirm=True)
    assert allocate_route.called
    # The allocate POST body must pin system_id="a" (lexically first),
    # not "z" (the first item MAAS happened to return).
    body = allocate_route.calls.last.request.content.decode(errors="replace")
    assert 'name="system_id"' in body and "a" in body
    assert result["system_id"] == "a"


@pytest.mark.asyncio
async def test_acquire_no_match_raises_value_error(monkeypatch) -> None:
    maas_client = _client(monkeypatch)
    with respx.mock(base_url=maas_client.base_url, assert_all_called=False) as mock:
        mock.get("/api/2.0/machines/", params={"limit": "200", "offset": "0"}).mock(
            return_value=Response(200, json=[])
        )
        async with maas_client:
            with pytest.raises(ValueError, match="no machine matches"):
                await AcquireMachineTool().run(maas_client, confirm=True)
