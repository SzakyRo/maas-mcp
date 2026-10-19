"""machine_delete: DELETE /machines/{system_id}/ with confirm gate."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from maasmcp.curated.machine_delete import MachineDeleteTool
from maasmcp.maas.client import MaasClient


@pytest.mark.asyncio
async def test_confirm_false_is_noop(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="confirm=True"):
                await MachineDeleteTool().run(maas_client, system_id="abc", confirm=False)
    assert not mock.calls


@pytest.mark.asyncio
async def test_confirm_omitted_is_noop(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="confirm=True"):
                await MachineDeleteTool().run(maas_client, system_id="abc")
    assert not mock.calls


@pytest.mark.asyncio
async def test_confirm_true_deletes_machine(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        route = mock.delete("/api/2.0/machines/abc/").mock(return_value=Response(204))
        async with maas_client:
            result = await MachineDeleteTool().run(maas_client, system_id="abc", confirm=True)
    assert route.call_count == 1
    assert result is None
    # confirm is a local gate only — it must never go over the wire.
    assert "confirm" not in route.calls.last.request.url.params
    assert route.calls.last.request.content == b""
