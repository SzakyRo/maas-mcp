"""set_boot_disk: POST op-set_boot_disk with confirm gate."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from maasmcp.curated.set_boot_disk import SetBootDiskTool
from maasmcp.maas.client import MaasClient


@pytest.mark.asyncio
async def test_confirm_false_is_noop(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="confirm=True"):
                await SetBootDiskTool().run(
                    maas_client, system_id="abc", block_device_id=1, confirm=False
                )
    assert not mock.calls


@pytest.mark.asyncio
async def test_confirm_true_sets_boot_disk(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        route = mock.post("/api/2.0/nodes/abc/blockdevices/1/op-set_boot_disk").mock(
            return_value=Response(200, json={})
        )
        async with maas_client:
            result = await SetBootDiskTool().run(
                maas_client, system_id="abc", block_device_id=1, confirm=True
            )
    assert route.call_count == 1
    assert result["status"] == "ok"
    assert result["operation"] == "set_boot_disk"


@pytest.mark.asyncio
async def test_sends_no_body_returns_text_ok(maas_client: MaasClient) -> None:
    """Real MAAS: set_boot_disk rejects an empty multipart body with 400 and
    returns literal ``OK`` text on success. The verb must POST without a body
    and the response parser must tolerate non-JSON success bodies.

    Regression guard for the 400 discovered on living-ewe 2026-07-08.
    """
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        route = mock.post("/api/2.0/nodes/abc/blockdevices/1/op-set_boot_disk").mock(
            return_value=Response(200, text="OK")
        )
        async with maas_client:
            result = await SetBootDiskTool().run(
                maas_client, system_id="abc", block_device_id=1, confirm=True
            )
    assert route.call_count == 1
    # Verb builds its own success dict locally; MAAS's "OK" response
    # is captured as text by MaasClient._parse_response but never leaks in.
    assert result["status"] == "ok"
    # The request was sent WITHOUT a multipart body (no Content-Type set by us).
    req = route.calls.last.request
    assert req.headers.get("content-type") is None


@pytest.mark.asyncio
async def test_empty_system_id_with_confirm_true_still_fails(
    maas_client: MaasClient,
) -> None:
    """Path validation must happen BEFORE the confirm check."""
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="system_id"):
                await SetBootDiskTool().run(
                    maas_client,
                    system_id="",
                    block_device_id=1,
                    confirm=True,
                )
    assert not mock.calls


@pytest.mark.asyncio
async def test_set_boot_disk_by_hostname(maas_client: MaasClient) -> None:
    """Hostname path: resolve then byte-identical upstream POST.

    Proves the hostname→system_id resolve happens and the actual upstream
    call shape is unchanged from the system_id path.
    """
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        resolve_route = mock.get(
            "/api/2.0/machines/", params={"hostname": "node-1"}
        ).mock(return_value=Response(200, json=[{"system_id": "xy7zab"}]))
        boot_route = mock.post(
            "/api/2.0/nodes/xy7zab/blockdevices/3/op-set_boot_disk"
        ).mock(return_value=Response(200, json={}))
        async with maas_client:
            result = await SetBootDiskTool().run(
                maas_client,
                hostname="node-1",
                block_device_id=3,
                confirm=True,
            )
    assert resolve_route.call_count == 1
    assert boot_route.call_count == 1
    assert result["status"] == "ok"
    assert result["operation"] == "set_boot_disk"
