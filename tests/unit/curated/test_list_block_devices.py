"""list_block_devices: GET /nodes/{system_id}/blockdevices/."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from maasmcp.curated.list_block_devices import ListBlockDevicesTool
from maasmcp.maas.client import MaasClient


@pytest.mark.asyncio
async def test_list_block_devices_returns_devices(maas_client: MaasClient) -> None:
    devices = [{"id": 1, "name": "sda", "size": 1000000}]
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        route = mock.get("/api/2.0/nodes/abc/blockdevices/").mock(
            return_value=Response(200, json=devices)
        )
        async with maas_client:
            result = await ListBlockDevicesTool().run(maas_client, system_id="abc")
    assert route.call_count == 1
    assert result == devices


@pytest.mark.asyncio
async def test_list_block_devices_handles_envelope(maas_client: MaasClient) -> None:
    """MAAS may return {"blockdevices": [...]}; unwrap to list."""
    devices = [{"id": 1, "name": "sda"}]
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        mock.get("/api/2.0/nodes/abc/blockdevices/").mock(
            return_value=Response(200, json={"blockdevices": devices})
        )
        async with maas_client:
            result = await ListBlockDevicesTool().run(maas_client, system_id="abc")
    assert result == devices


@pytest.mark.asyncio
async def test_empty_system_id_raises_value_error(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="system_id"):
                await ListBlockDevicesTool().run(maas_client, system_id="")
    assert not mock.calls


@pytest.mark.asyncio
async def test_list_block_devices_by_hostname(maas_client: MaasClient) -> None:
    """Hostname path: resolve then byte-identical upstream GET.

    Proves the hostname→system_id resolve happens and the actual upstream
    call shape is unchanged from the system_id path.
    """
    devices = [{"id": 1, "name": "sda", "size": 1000000}]
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        resolve_route = mock.get(
            "/api/2.0/machines/", params={"hostname": "node-1"}
        ).mock(return_value=Response(200, json=[{"system_id": "xy7zab"}]))
        list_route = mock.get("/api/2.0/nodes/xy7zab/blockdevices/").mock(
            return_value=Response(200, json=devices)
        )
        async with maas_client:
            result = await ListBlockDevicesTool().run(maas_client, hostname="node-1")
    assert resolve_route.call_count == 1
    assert list_route.call_count == 1
    assert result == devices
