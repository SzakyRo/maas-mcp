"""list_raids: GET /nodes/{system_id}/raids/."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from maasmcp.curated.list_raids import ListRaidsTool
from maasmcp.maas.client import MaasClient


@pytest.mark.asyncio
async def test_list_raids_returns_list(maas_client: MaasClient) -> None:
    raids = [{"id": 1, "name": "md0", "level": 1}]
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        route = mock.get("/api/2.0/nodes/abc/raids/").mock(return_value=Response(200, json=raids))
        async with maas_client:
            result = await ListRaidsTool().run(maas_client, system_id="abc")
    assert route.call_count == 1
    assert result == raids


@pytest.mark.asyncio
async def test_empty_system_id_raises_value_error(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="system_id"):
                await ListRaidsTool().run(maas_client, system_id="")
    assert not mock.calls
