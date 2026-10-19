"""machines_create: POST /machines/ with confirm gate."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from maasmcp.curated.machines_create import MachinesCreateTool
from maasmcp.maas.client import MaasClient


@pytest.mark.asyncio
async def test_confirm_false_is_noop(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="confirm=True"):
                await MachinesCreateTool().run(
                    maas_client,
                    architecture="amd64",
                    mac_addresses="01:02:03:04:05:06",
                    confirm=False,
                )
    assert not mock.calls


@pytest.mark.asyncio
async def test_confirm_true_posts_only_set_fields(maas_client: MaasClient) -> None:
    payload = {"system_id": "abc", "hostname": "h-abc"}
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        route = mock.post("/api/2.0/machines/").mock(return_value=Response(200, json=payload))
        async with maas_client:
            result = await MachinesCreateTool().run(
                maas_client,
                architecture="amd64",
                mac_addresses="01:02:03:04:05:06",
                hostname="h-abc",
                commission=True,
                enable_ssh=1,
                confirm=True,
            )
    assert route.call_count == 1
    assert result == payload
    req = route.calls.last.request
    assert req.url.path.endswith("/api/2.0/machines/")
    # MAAS gets multipart bodies; assert field names on the raw bytes.
    body = req.content
    assert b'name="architecture"' in body
    assert b"amd64" in body
    assert b'name="mac_addresses"' in body
    assert b'name="hostname"' in body
    assert b'name="commission"' in body
    assert b"true" in body  # booleans render as lowercase for MAAS
    assert b'name="enable_ssh"' in body
    # Unset fields and the local confirm flag must not go over the wire.
    assert b'name="confirm"' not in body
    assert b'name="power_type"' not in body
    assert b'name="skip_storage"' not in body
