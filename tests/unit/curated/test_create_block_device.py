"""create_block_device: POST with confirm gate."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from maasmcp.curated.create_block_device import CreateBlockDeviceTool
from maasmcp.maas.client import MaasClient
from maasmcp.maas.errors import MCPUpstreamError


@pytest.mark.asyncio
async def test_confirm_false_is_noop(maas_client: MaasClient) -> None:
    """Safety gate: confirm=False raises ValueError before any MAAS call."""
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="confirm=True"):
                await CreateBlockDeviceTool().run(
                    maas_client,
                    system_id="abc",
                    name="sda",
                    size="1000000",
                    block_size="512",
                    confirm=False,
                )
    # Critical: no MAAS request was issued.
    assert not mock.calls


@pytest.mark.asyncio
async def test_confirm_true_creates_device(maas_client: MaasClient) -> None:
    device = {"id": 1, "name": "sda", "size": 1000000}
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        route = mock.post("/api/2.0/nodes/abc/blockdevices/").mock(
            return_value=Response(200, json=device)
        )
        async with maas_client:
            result = await CreateBlockDeviceTool().run(
                maas_client,
                system_id="abc",
                name="sda",
                size="1000000",
                block_size="512",
                confirm=True,
            )
    assert route.call_count == 1
    assert result == device


@pytest.mark.asyncio
async def test_empty_system_id_with_confirm_true_still_fails(
    maas_client: MaasClient,
) -> None:
    """Path validation must happen BEFORE the confirm check."""
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="system_id"):
                await CreateBlockDeviceTool().run(
                    maas_client,
                    system_id="",
                    name="sda",
                    size="1000000",
                    block_size="512",
                    confirm=True,
                )
    assert not mock.calls


@pytest.mark.asyncio
async def test_409_surfaces_as_upstream_error(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        mock.post("/api/2.0/nodes/abc/blockdevices/").mock(
            return_value=Response(409, text="machine not ready")
        )
        async with maas_client:
            with pytest.raises(MCPUpstreamError) as exc_info:
                await CreateBlockDeviceTool().run(
                    maas_client,
                    system_id="abc",
                    name="sda",
                    size="1000000",
                    block_size="512",
                    confirm=True,
                )
    # Body is stripped (security fix 5ad4a1a). Assert on status code only.
    assert "409" in str(exc_info.value)
