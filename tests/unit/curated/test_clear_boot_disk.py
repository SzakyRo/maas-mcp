"""clear_boot_disk: MAAS has no clear verb, so the tool surfaces the gap
as structured data instead of making a fake call."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from maasmcp.curated.clear_boot_disk import ClearBootDiskTool
from maasmcp.maas.client import MaasClient


@pytest.mark.asyncio
async def test_confirm_false_raises(maas_client: MaasClient) -> None:
    """The gate is intentional — the caller is asking the MCP to 'try to
    clear', so we require explicit confirm even though no destructive
    action is performed."""
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="confirm=True"):
                await ClearBootDiskTool().run(maas_client, system_id="abc", confirm=False)
    assert not mock.calls


@pytest.mark.asyncio
async def test_empty_system_id_raises_before_maas_call(
    maas_client: MaasClient,
) -> None:
    """Path validation must happen before the confirm check."""
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="system_id"):
                await ClearBootDiskTool().run(maas_client, system_id="", confirm=True)
    assert not mock.calls


@pytest.mark.asyncio
async def test_noop_when_no_boot_disk_pinned(maas_client: MaasClient) -> None:
    """Machine has no boot_disk field — tool reports a no-op and returns
    no workarounds."""
    machine_payload = {
        "system_id": "abc",
        "hostname": "rich-gator",
        "pool": {"name": "default"},
        "owner": {"username": "admin"},
        "power_state": "off",
        "osystem": "",
        "distro_series": "",
        "last_commissioned": None,
        "boot_disk": None,
    }
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        route = mock.get("/api/2.0/machines/abc/").mock(
            return_value=Response(200, json=machine_payload)
        )
        async with maas_client:
            result = await ClearBootDiskTool().run(maas_client, system_id="abc", confirm=True)
    assert route.call_count == 1
    assert result["status"] == "noop"
    assert result["system_id"] == "abc"
    assert result["operation"] == "clear_boot_disk"
    assert result["current_boot_disk"] == {
        "boot_disk_id": None,
        "boot_disk_name": None,
        "boot_disk_path": None,
    }
    assert result["available_workarounds"] == []
    assert "nothing to clear" in result["reason"]


@pytest.mark.asyncio
async def test_unsupported_when_boot_disk_pinned_as_dict(
    maas_client: MaasClient,
) -> None:
    """MAAS returns boot_disk as an embedded block-device dict on the
    singular endpoint. Tool normalizes and surfaces workarounds."""
    machine_payload = {
        "system_id": "abc",
        "hostname": "rich-gator",
        "boot_disk": {
            "id": 1,
            "name": "sda",
            "path": "/dev/sda",
            "id_path": "/dev/disk/by-id/wwn-0x5000",
        },
    }
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        route = mock.get("/api/2.0/machines/abc/").mock(
            return_value=Response(200, json=machine_payload)
        )
        async with maas_client:
            result = await ClearBootDiskTool().run(maas_client, system_id="abc", confirm=True)
    assert route.call_count == 1
    assert result["status"] == "unsupported"
    assert result["current_boot_disk"]["boot_disk_id"] == 1
    assert result["current_boot_disk"]["boot_disk_name"] == "sda"
    assert result["current_boot_disk"]["boot_disk_path"] == "/dev/sda"
    assert "405" in result["reason"]
    assert "BlockDeviceHandler_set_boot_disk" in result["reason"]
    workarounds = result["available_workarounds"]
    assert len(workarounds) == 3
    assert workarounds[0]["name"] == "release_and_redeploy"
    assert workarounds[0]["destructive"] is True
    assert "release_machine" in workarounds[0]["verbs"]
    assert "deploy_machine" in workarounds[0]["verbs"]
    assert workarounds[1]["name"] == "leave_pinned"
    assert workarounds[1]["destructive"] is False
    assert workarounds[2]["name"] == "delete_and_reenlist"
    assert "machine_delete" in workarounds[2]["verbs"]


@pytest.mark.asyncio
async def test_unsupported_when_boot_disk_pinned_as_int(
    maas_client: MaasClient,
) -> None:
    """Some paginated paths return boot_disk as a scalar id. Tool must
    handle that shape without crashing."""
    machine_payload = {
        "system_id": "abc",
        "boot_disk": 7,
    }
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        route = mock.get("/api/2.0/machines/abc/").mock(
            return_value=Response(200, json=machine_payload)
        )
        async with maas_client:
            result = await ClearBootDiskTool().run(maas_client, system_id="abc", confirm=True)
    assert route.call_count == 1
    assert result["status"] == "unsupported"
    assert result["current_boot_disk"]["boot_disk_id"] == 7
    assert result["current_boot_disk"]["boot_disk_name"] is None
    assert result["current_boot_disk"]["boot_disk_path"] is None
    assert len(result["available_workarounds"]) == 3


@pytest.mark.asyncio
async def test_does_not_write_to_maas(maas_client: MaasClient) -> None:
    """Hard guarantee: this tool must NEVER issue a POST/PUT/DELETE.
    The gap is unsolvable upstream; the tool's job is to surface it.

    clear_boot_disk always fetches via GET /machines/{system_id}/ —
    no routing heuristic, unlike get_machine."""
    _SYSTEM_ID = "abcdef"
    machine_payload = {
        "system_id": _SYSTEM_ID,
        "boot_disk": {"id": 1, "name": "sda"},
    }
    with respx.mock(
        base_url=maas_client.base_url,  # type: ignore[attr-defined]
        assert_all_called=False,  # routes registered but expected to NOT be hit
    ) as mock:
        read = mock.get(f"/api/2.0/machines/{_SYSTEM_ID}/").mock(
            return_value=Response(200, json=machine_payload)
        )
        # Any write method to any machine path would be a regression.
        post = mock.post(f"/api/2.0/machines/{_SYSTEM_ID}/").mock(
            return_value=Response(200, json={})
        )
        put = mock.put(f"/api/2.0/machines/{_SYSTEM_ID}/").mock(return_value=Response(200, json={}))
        delete = mock.delete(f"/api/2.0/machines/{_SYSTEM_ID}/").mock(return_value=Response(204))
        async with maas_client:
            result = await ClearBootDiskTool().run(maas_client, system_id=_SYSTEM_ID, confirm=True)
    assert read.call_count == 1
    assert post.call_count == 0
    assert put.call_count == 0
    assert delete.call_count == 0
    assert result["status"] == "unsupported"
