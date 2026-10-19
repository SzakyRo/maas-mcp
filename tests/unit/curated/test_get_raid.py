"""get_raid: GET /nodes/{system_id}/raid/{id}/."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from maasmcp.curated.get_raid import GetRaidTool
from maasmcp.maas.client import MaasClient


@pytest.mark.asyncio
async def test_get_raid_returns_dict(maas_client: MaasClient) -> None:
    raid = {"id": 7, "name": "md0", "level": 1}
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        route = mock.get("/api/2.0/nodes/abc/raid/7/").mock(return_value=Response(200, json=raid))
        async with maas_client:
            result = await GetRaidTool().run(maas_client, system_id="abc", raid_id=7)
    assert route.call_count == 1
    assert result == raid


@pytest.mark.asyncio
async def test_empty_system_id_raises_value_error(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="system_id"):
                await GetRaidTool().run(maas_client, system_id="", raid_id=1)
    assert not mock.calls


@pytest.mark.asyncio
async def test_raid_id_zero_raises_value_error(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="raid_id"):
                await GetRaidTool().run(maas_client, system_id="abc", raid_id=0)
    assert not mock.calls


@pytest.mark.asyncio
async def test_get_raid_non_dict_response_raises(maas_client: MaasClient) -> None:
    """Schema drift: MAAS 200 with a non-dict body should not silently return {}."""
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        route = mock.get("/api/2.0/nodes/abc/raid/7/").mock(
            return_value=Response(200, json=[{"unexpected": "list"}])
        )
        async with maas_client:
            with pytest.raises(ValueError, match="non-dict"):
                await GetRaidTool().run(maas_client, system_id="abc", raid_id=7)
    assert route.call_count == 1
