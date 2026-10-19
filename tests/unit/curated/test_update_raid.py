"""update_raid: PUT /nodes/{system_id}/raid/{id}/ with confirm gate."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from maasmcp.curated.update_raid import UpdateRaidTool
from maasmcp.maas.client import MaasClient


@pytest.mark.asyncio
async def test_confirm_false_is_noop(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="confirm=True"):
                await UpdateRaidTool().run(
                    maas_client,
                    system_id="abc",
                    raid_id=1,
                    name="md0",
                    confirm=False,
                )
    assert not mock.calls


@pytest.mark.asyncio
async def test_confirm_true_updates_raid(maas_client: MaasClient) -> None:
    raid = {"id": 1, "name": "md0-renamed"}
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        route = mock.put("/api/2.0/nodes/abc/raid/1/").mock(return_value=Response(200, json=raid))
        async with maas_client:
            result = await UpdateRaidTool().run(
                maas_client,
                system_id="abc",
                raid_id=1,
                name="md0-renamed",
                confirm=True,
            )
    assert route.call_count == 1
    assert result == raid


@pytest.mark.asyncio
async def test_no_update_fields_raises_without_put(maas_client: MaasClient) -> None:
    """All optional args None must fail fast (no empty-body PUT), as with
    update_vlan/update_interface."""
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="nothing to update"):
                await UpdateRaidTool().run(
                    maas_client,
                    system_id="abc",
                    raid_id=1,
                    confirm=True,
                )
    assert not mock.calls


@pytest.mark.asyncio
async def test_empty_system_id_with_confirm_true_still_fails(
    maas_client: MaasClient,
) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="system_id"):
                await UpdateRaidTool().run(
                    maas_client,
                    system_id="",
                    raid_id=1,
                    name="md0",
                    confirm=True,
                )
    assert not mock.calls


@pytest.mark.asyncio
async def test_raid_id_zero_raises(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="raid_id"):
                await UpdateRaidTool().run(
                    maas_client,
                    system_id="abc",
                    raid_id=0,
                    confirm=True,
                )
    assert not mock.calls


@pytest.mark.asyncio
async def test_update_raid_non_dict_response_raises(
    maas_client: MaasClient,
) -> None:
    """Schema drift: MAAS 200 with a non-dict body should not silently return {}."""
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        route = mock.put("/api/2.0/nodes/abc/raid/1/").mock(
            return_value=Response(200, json=["unexpected"])
        )
        async with maas_client:
            with pytest.raises(ValueError, match="non-dict"):
                await UpdateRaidTool().run(
                    maas_client,
                    system_id="abc",
                    raid_id=1,
                    name="md0",
                    confirm=True,
                )
    assert route.call_count == 1
