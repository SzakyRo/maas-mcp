"""create_raid: POST /nodes/{system_id}/raids/ with confirm gate."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from maasmcp.curated.create_raid import CreateRaidTool
from maasmcp.maas.client import MaasClient
from maasmcp.maas.errors import MCPUpstreamError


@pytest.mark.asyncio
async def test_confirm_false_is_noop(maas_client: MaasClient) -> None:
    """Safety gate: confirm=False raises before any MAAS call."""
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="confirm=True"):
                await CreateRaidTool().run(
                    maas_client,
                    system_id="abc",
                    level=1,
                    block_devices=[1, 2],
                    confirm=False,
                )
    assert not mock.calls


@pytest.mark.asyncio
async def test_confirm_true_creates_raid(maas_client: MaasClient) -> None:
    raid = {"id": 1, "name": "md0", "level": 1}
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        route = mock.post("/api/2.0/nodes/abc/raids/").mock(return_value=Response(200, json=raid))
        async with maas_client:
            result = await CreateRaidTool().run(
                maas_client,
                system_id="abc",
                level=1,
                block_devices=[1, 2],
                confirm=True,
            )
    assert route.call_count == 1
    assert result == raid


@pytest.mark.asyncio
async def test_invalid_level_raises(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="level"):
                await CreateRaidTool().run(
                    maas_client,
                    system_id="abc",
                    level=7,
                    block_devices=[1],
                    confirm=True,
                )
    assert not mock.calls


@pytest.mark.asyncio
async def test_missing_members_raises(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="block device or partition"):
                await CreateRaidTool().run(
                    maas_client,
                    system_id="abc",
                    level=1,
                    confirm=True,
                )
    assert not mock.calls


@pytest.mark.asyncio
async def test_empty_system_id_with_confirm_true_still_fails(
    maas_client: MaasClient,
) -> None:
    """Path validation must happen BEFORE the confirm check."""
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="system_id"):
                await CreateRaidTool().run(
                    maas_client,
                    system_id="",
                    level=1,
                    block_devices=[1],
                    confirm=True,
                )
    assert not mock.calls


@pytest.mark.asyncio
async def test_create_raid_non_dict_response_raises(
    maas_client: MaasClient,
) -> None:
    """Schema drift: MAAS 200 with a non-dict body should not silently return {}."""
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        route = mock.post("/api/2.0/nodes/abc/raids/").mock(
            return_value=Response(200, json=["unexpected"])
        )
        async with maas_client:
            with pytest.raises(ValueError, match="non-dict"):
                await CreateRaidTool().run(
                    maas_client,
                    system_id="abc",
                    level=1,
                    block_devices=[1],
                    confirm=True,
                )
    assert route.call_count == 1


@pytest.mark.asyncio
async def test_409_surfaces_as_upstream_error(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        mock.post("/api/2.0/nodes/abc/raids/").mock(
            return_value=Response(409, text="machine not ready")
        )
        async with maas_client:
            with pytest.raises(MCPUpstreamError) as exc_info:
                await CreateRaidTool().run(
                    maas_client,
                    system_id="abc",
                    level=1,
                    block_devices=[1],
                    confirm=True,
                )
    # Body is stripped (security fix 5ad4a1a). Assert on status code only.
    assert "409" in str(exc_info.value)


@pytest.mark.asyncio
async def test_level_translated_to_maas_string(maas_client: MaasClient) -> None:
    """MAAS accepts ``level`` only as a string enum (raid-0..raid-10).

    Integer 1 is rejected upstream with "Select a valid choice" — the public
    verb accepts the integer for ergonomics and translates at the wire
    boundary. Regression guard for the discovery on 2026-07-08.
    """
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        route = mock.post("/api/2.0/nodes/abc/raids/").mock(
            return_value=Response(200, json={"id": 7, "name": "md0"})
        )
        async with maas_client:
            await CreateRaidTool().run(
                maas_client,
                system_id="abc",
                level=1,
                partitions=[2, 3],
                confirm=True,
            )
    assert route.call_count == 1
    body = route.calls.last.request.content.decode()
    level_part = next(p for p in body.split("--") if 'name="level"' in p)
    assert level_part.rstrip().endswith("raid-1")


@pytest.mark.asyncio
async def test_create_raid_by_hostname(maas_client: MaasClient) -> None:
    """Hostname path: resolve then byte-identical upstream POST.

    Proves the hostname→system_id resolve happens and the actual upstream
    call shape is unchanged from the system_id path.
    """
    raid = {"id": 1, "name": "md0", "level": 1}
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        resolve_route = mock.get(
            "/api/2.0/machines/", params={"hostname": "node-1"}
        ).mock(return_value=Response(200, json=[{"system_id": "xy7zab"}]))
        create_route = mock.post("/api/2.0/nodes/xy7zab/raids/").mock(
            return_value=Response(200, json=raid)
        )
        async with maas_client:
            result = await CreateRaidTool().run(
                maas_client,
                hostname="node-1",
                level=1,
                block_devices=[1, 2],
                confirm=True,
            )
    assert resolve_route.call_count == 1
    assert create_route.call_count == 1
    assert result == raid
