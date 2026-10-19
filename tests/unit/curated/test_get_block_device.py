"""get_block_device: GET /nodes/{system_id}/blockdevices/{id}/."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from maasmcp.curated.get_block_device import GetBlockDeviceTool
from maasmcp.maas.client import MaasClient
from maasmcp.maas.errors import MCPUpstreamError


@pytest.mark.asyncio
async def test_get_block_device_returns_dict(maas_client: MaasClient) -> None:
    device = {"id": 7, "name": "sda", "size": 1000000}
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        route = mock.get("/api/2.0/nodes/abc/blockdevices/7/").mock(
            return_value=Response(200, json=device)
        )
        async with maas_client:
            result = await GetBlockDeviceTool().run(maas_client, system_id="abc", block_device_id=7)
    assert route.call_count == 1
    assert result == device


@pytest.mark.asyncio
async def test_get_block_device_404_surfaces_as_upstream_error(
    maas_client: MaasClient,
) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        mock.get("/api/2.0/nodes/abc/blockdevices/99/").mock(
            return_value=Response(404, text="not found")
        )
        async with maas_client:
            with pytest.raises(MCPUpstreamError) as exc_info:
                await GetBlockDeviceTool().run(maas_client, system_id="abc", block_device_id=99)
    # Security fix 5ad4a1a: body is stripped. Assert on status code only.
    assert "404" in str(exc_info.value)


@pytest.mark.asyncio
async def test_empty_system_id_raises_value_error(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="system_id"):
                await GetBlockDeviceTool().run(maas_client, system_id="", block_device_id=1)
    assert not mock.calls


@pytest.mark.asyncio
async def test_block_device_id_zero_raises_value_error(
    maas_client: MaasClient,
) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="block_device_id"):
                await GetBlockDeviceTool().run(maas_client, system_id="abc", block_device_id=0)
    assert not mock.calls


@pytest.mark.asyncio
async def test_get_block_device_non_dict_response_raises(
    maas_client: MaasClient,
) -> None:
    """Schema drift: MAAS 200 with a non-dict body should not silently return {}."""
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        route = mock.get("/api/2.0/nodes/abc/blockdevices/7/").mock(
            return_value=Response(200, json=[{"unexpected": "list"}])
        )
        async with maas_client:
            with pytest.raises(ValueError, match="non-dict"):
                await GetBlockDeviceTool().run(maas_client, system_id="abc", block_device_id=7)
    assert route.call_count == 1
