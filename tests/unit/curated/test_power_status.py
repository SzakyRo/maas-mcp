"""Tests for PowerStatusTool — including the hostname→system_id resolution path."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from maasmcp.config import MaasmcpConfig
from maasmcp.curated.power_status import PowerStatusTool
from maasmcp.maas.client import MaasClient

pytestmark = pytest.mark.asyncio


async def test_power_status_by_hostname(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url, assert_all_called=False) as mock:
        mock.get("/api/2.0/machines/", params={"hostname": "node-1"}).mock(
            return_value=Response(200, json=[{"system_id": "xy7zab"}])
        )
        mock.get("/api/2.0/machines/xy7zab/").mock(
            return_value=Response(200, json={"power_state": "on"})
        )
        async with maas_client:
            result = await PowerStatusTool().run(maas_client, hostname="node-1")
    assert result == "on"


async def test_power_status_neither_id_nor_hostname(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    async with maas_client:
        with pytest.raises(ValueError, match="at least one of system_id or hostname"):
            await PowerStatusTool().run(maas_client)
