"""unmount_block_device: op-unmount on a whole block device."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from maasmcp.config import MaasmcpConfig
from maasmcp.curated.unmount_block_device import UnmountBlockDeviceTool
from maasmcp.maas.client import MaasClient

pytestmark = pytest.mark.asyncio


def _client(monkeypatch: pytest.MonkeyPatch) -> MaasClient:
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    return maas_client


async def test_unmount_happy(monkeypatch):
    maas_client = _client(monkeypatch)
    with respx.mock(base_url=maas_client.base_url) as mock:
        route = mock.post("/api/2.0/nodes/abc/blockdevices/50/op-unmount").mock(
            return_value=Response(200, json={})
        )
        async with maas_client:
            result = await UnmountBlockDeviceTool().run(
                maas_client, system_id="abc", block_device_id=50, confirm=True
            )
    assert route.called
    assert result == {
        "status": "ok",
        "system_id": "abc",
        "resource_id": 50,
        "operation": "unmount",
    }


async def test_unmount_requires_confirm(monkeypatch):
    maas_client = _client(monkeypatch)
    with respx.mock(base_url=maas_client.base_url) as mock:
        async with maas_client:
            with pytest.raises(ValueError, match="confirm=True"):
                await UnmountBlockDeviceTool().run(
                    maas_client, system_id="abc", block_device_id=50, confirm=False
                )
    assert not mock.calls
