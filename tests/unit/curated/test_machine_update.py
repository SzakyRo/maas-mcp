"""machine_update: PUT /machines/{system_id}/ with confirm gate."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from maasmcp.curated.machine_update import MachineUpdateTool
from maasmcp.maas.client import MaasClient


@pytest.mark.asyncio
async def test_confirm_false_is_noop(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="confirm=True"):
                await MachineUpdateTool().run(
                    maas_client, system_id="abc", hostname="new-name", confirm=False
                )
    assert not mock.calls


@pytest.mark.asyncio
async def test_confirm_true_puts_only_set_fields(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        route = mock.put("/api/2.0/machines/abc/").mock(
            return_value=Response(200, json={"system_id": "abc", "hostname": "new-name"})
        )
        async with maas_client:
            result = await MachineUpdateTool().run(
                maas_client,
                system_id="abc",
                hostname="new-name",
                memory="32G",
                confirm=True,
            )
    assert route.call_count == 1
    assert result["hostname"] == "new-name"
    # MAAS gets multipart bodies; assert field names on the raw bytes.
    body = route.calls.last.request.content
    assert b'name="hostname"' in body
    assert b'name="memory"' in body
    assert b"32G" in body
    # Unset fields and the local confirm flag must not go over the wire.
    assert b'name="confirm"' not in body
    assert b'name="zone"' not in body
    assert b'name="cpu_count"' not in body
