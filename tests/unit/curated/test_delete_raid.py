"""delete_raid: DELETE /nodes/{system_id}/raid/{id}/ with confirm gate."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from maasmcp.curated.delete_raid import DeleteRaidTool
from maasmcp.maas.client import MaasClient


@pytest.mark.asyncio
async def test_confirm_false_is_noop(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="confirm=True"):
                await DeleteRaidTool().run(maas_client, system_id="abc", raid_id=1, confirm=False)
    assert not mock.calls


@pytest.mark.asyncio
async def test_confirm_true_deletes_raid(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        route = mock.delete("/api/2.0/nodes/abc/raid/1/").mock(return_value=Response(204))
        async with maas_client:
            result = await DeleteRaidTool().run(
                maas_client, system_id="abc", raid_id=1, confirm=True
            )
    assert route.call_count == 1
    assert result is None or result == {}


@pytest.mark.asyncio
async def test_empty_system_id_with_confirm_true_still_fails(
    maas_client: MaasClient,
) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="system_id"):
                await DeleteRaidTool().run(maas_client, system_id="", raid_id=1, confirm=True)
    assert not mock.calls
