"""delete_volume_group: DELETE /nodes/{system_id}/volume-group/{id}/ with confirm gate."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from maasmcp.curated.delete_volume_group import DeleteVolumeGroupTool
from maasmcp.maas.client import MaasClient


@pytest.mark.asyncio
async def test_confirm_false_is_noop(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="confirm=True"):
                await DeleteVolumeGroupTool().run(
                    maas_client, system_id="abc", vg_id=1, confirm=False
                )
    assert not mock.calls


@pytest.mark.asyncio
async def test_confirm_true_deletes_volume_group(
    maas_client: MaasClient,
) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        route = mock.delete("/api/2.0/nodes/abc/volume-group/1/").mock(return_value=Response(204))
        async with maas_client:
            result = await DeleteVolumeGroupTool().run(
                maas_client, system_id="abc", vg_id=1, confirm=True
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
                await DeleteVolumeGroupTool().run(maas_client, system_id="", vg_id=1, confirm=True)
    assert not mock.calls
