"""storage_summary: two-stage fetch, parallel partition reads."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from maasmcp.curated.storage_summary import StorageSummaryTool
from maasmcp.maas.client import MaasClient


@pytest.mark.asyncio
async def test_storage_summary_happy_path(maas_client: MaasClient) -> None:
    devices = [
        {"id": 1, "size": 100 * 1024**3},  # 100 GiB
        {"id": 2, "size": 200 * 1024**3},  # 200 GiB
    ]
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        mock.get("/api/2.0/nodes/abc/blockdevices/").mock(return_value=Response(200, json=devices))
        mock.get("/api/2.0/nodes/abc/blockdevices/1/partitions/").mock(
            return_value=Response(200, json=[{"id": 10}, {"id": 11}])
        )
        mock.get("/api/2.0/nodes/abc/blockdevices/2/partitions/").mock(
            return_value=Response(200, json=[{"id": 20}])
        )
        mock.get("/api/2.0/nodes/abc/raids/").mock(return_value=Response(200, json=[]))
        mock.get("/api/2.0/nodes/abc/volume-groups/").mock(return_value=Response(200, json=[]))
        async with maas_client:
            result = await StorageSummaryTool().run(maas_client, system_id="abc")
    assert result["system_id"] == "abc"
    assert result["block_devices"] == 2
    assert result["partitions"] == 3
    assert result["total_size_gib"] == 300.0
    assert result["raid_devices"] == 0
    assert result["volume_groups"] == 0
    assert result["logical_volumes"] == 0


@pytest.mark.asyncio
async def test_storage_summary_handles_no_devices(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        mock.get("/api/2.0/nodes/abc/blockdevices/").mock(return_value=Response(200, json=[]))
        mock.get("/api/2.0/nodes/abc/raids/").mock(return_value=Response(200, json=[]))
        mock.get("/api/2.0/nodes/abc/volume-groups/").mock(return_value=Response(200, json=[]))
        async with maas_client:
            result = await StorageSummaryTool().run(maas_client, system_id="abc")
    assert result["block_devices"] == 0
    assert result["partitions"] == 0
    assert result["total_size_gib"] == 0.0


@pytest.mark.asyncio
async def test_storage_summary_handles_envelope(maas_client: MaasClient) -> None:
    devices = [{"id": 1, "size": 50 * 1024**3}]
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        mock.get("/api/2.0/nodes/abc/blockdevices/").mock(
            return_value=Response(200, json={"blockdevices": devices})
        )
        mock.get("/api/2.0/nodes/abc/blockdevices/1/partitions/").mock(
            return_value=Response(200, json={"partitions": [{"id": 10}]})
        )
        mock.get("/api/2.0/nodes/abc/raids/").mock(return_value=Response(200, json=[]))
        mock.get("/api/2.0/nodes/abc/volume-groups/").mock(return_value=Response(200, json=[]))
        async with maas_client:
            result = await StorageSummaryTool().run(maas_client, system_id="abc")
    assert result["block_devices"] == 1
    assert result["partitions"] == 1


@pytest.mark.asyncio
async def test_storage_summary_handles_raids_vg_envelope(
    maas_client: MaasClient,
) -> None:
    """Wrapped {"raids": [...]} and {"volume_groups": [...]} shapes parse correctly."""
    devices = [{"id": 1, "size": 50 * 1024**3}]
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        mock.get("/api/2.0/nodes/abc/blockdevices/").mock(return_value=Response(200, json=devices))
        mock.get("/api/2.0/nodes/abc/blockdevices/1/partitions/").mock(
            return_value=Response(200, json=[])
        )
        mock.get("/api/2.0/nodes/abc/raids/").mock(
            return_value=Response(200, json={"raids": [{"id": 10, "name": "md0", "level": 1}]})
        )
        mock.get("/api/2.0/nodes/abc/volume-groups/").mock(
            return_value=Response(200, json={"volume_groups": [{"id": 20, "name": "vg0"}]})
        )
        async with maas_client:
            result = await StorageSummaryTool().run(maas_client, system_id="abc")
    assert result["raid_devices"] == 1
    assert result["volume_groups"] == 1


@pytest.mark.asyncio
async def test_empty_system_id_raises_value_error(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="system_id"):
                await StorageSummaryTool().run(maas_client, system_id="")
    assert not mock.calls


@pytest.mark.asyncio
async def test_storage_summary_counts_raids_vgs_and_lvs(
    maas_client: MaasClient,
) -> None:
    """Stage 2 must include raids + volume-groups; LVs summed across VGs."""
    devices = [{"id": 1, "size": 50 * 1024**3}]
    raids = [{"id": 10, "name": "md0", "level": 1}]
    vgs = [
        {"id": 20, "name": "vg0", "logical_volumes": [{"id": 100}, {"id": 101}]},
        {"id": 21, "name": "vg1", "logical_volumes": [{"id": 200}]},
    ]
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        mock.get("/api/2.0/nodes/abc/blockdevices/").mock(return_value=Response(200, json=devices))
        mock.get("/api/2.0/nodes/abc/blockdevices/1/partitions/").mock(
            return_value=Response(200, json=[])
        )
        mock.get("/api/2.0/nodes/abc/raids/").mock(return_value=Response(200, json=raids))
        mock.get("/api/2.0/nodes/abc/volume-groups/").mock(return_value=Response(200, json=vgs))
        async with maas_client:
            result = await StorageSummaryTool().run(maas_client, system_id="abc")
    assert result["raid_devices"] == 1
    assert result["volume_groups"] == 2
    assert result["logical_volumes"] == 3


@pytest.mark.asyncio
async def test_storage_summary_lv_count_falls_back_to_volumes_key(
    maas_client: MaasClient,
) -> None:
    devices = [{"id": 1, "size": 10 * 1024**3}]
    vgs = [{"id": 20, "name": "vg0", "volumes": [{"id": 100}]}]
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        mock.get("/api/2.0/nodes/abc/blockdevices/").mock(return_value=Response(200, json=devices))
        mock.get("/api/2.0/nodes/abc/blockdevices/1/partitions/").mock(
            return_value=Response(200, json=[])
        )
        mock.get("/api/2.0/nodes/abc/raids/").mock(return_value=Response(200, json=[]))
        mock.get("/api/2.0/nodes/abc/volume-groups/").mock(return_value=Response(200, json=vgs))
        async with maas_client:
            result = await StorageSummaryTool().run(maas_client, system_id="abc")
    assert result["logical_volumes"] == 1
