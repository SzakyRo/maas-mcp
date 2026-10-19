import pytest
import respx
from httpx import Response

from maasmcp.config import MaasmcpConfig
from maasmcp.curated.unlink_subnet import UnlinkSubnetTool
from maasmcp.maas.client import MaasClient

pytestmark = pytest.mark.asyncio


async def test_unlink_subnet_happy(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url) as mock:
        route = mock.post("/api/2.0/nodes/abc123/interfaces/8/op-unlink_subnet").mock(
            return_value=Response(200, json={"id": 8})
        )
        async with maas_client:
            result = await UnlinkSubnetTool().run(
                maas_client, system_id="abc123", iface_id=8, link_id=977, confirm=True
            )
    assert result == {"id": 8}
    assert route.called
    # MAAS's unlink op takes the LINK id (docs: "ID of the subnet link"),
    # never a bare subnet id — pin the multipart body.
    body = route.calls[0].request.content.decode(errors="replace")
    assert 'name="id"' in body
    assert "977" in body
    assert 'name="subnet"' not in body


async def test_unlink_subnet_legacy_subnet_fallback(monkeypatch):
    """subnet_id without link_id keeps the old `subnet` body param for
    older MAAS releases."""
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url) as mock:
        route = mock.post("/api/2.0/nodes/abc123/interfaces/8/op-unlink_subnet").mock(
            return_value=Response(200, json={"id": 8})
        )
        async with maas_client:
            result = await UnlinkSubnetTool().run(
                maas_client, system_id="abc123", iface_id=8, subnet_id=5, confirm=True
            )
    assert result == {"id": 8}
    body = route.calls[0].request.content.decode(errors="replace")
    assert 'name="subnet"' in body


async def test_unlink_subnet_requires_link_or_subnet(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    async with maas_client:
        with pytest.raises(ValueError, match="requires link_id"):
            await UnlinkSubnetTool().run(maas_client, system_id="abc123", iface_id=8, confirm=True)


async def test_unlink_subnet_requires_confirm(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    async with maas_client:
        with pytest.raises(ValueError, match="confirm=True"):
            await UnlinkSubnetTool().run(
                maas_client, system_id="abc123", iface_id=8, link_id=977, confirm=False
            )


async def test_unlink_subnet_non_dict_raises(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url) as mock:
        mock.post("/api/2.0/nodes/abc123/interfaces/8/op-unlink_subnet").mock(
            return_value=Response(200, json="bad")
        )
        async with maas_client:
            with pytest.raises(ValueError, match="non-dict"):
                await UnlinkSubnetTool().run(
                    maas_client, system_id="abc123", iface_id=8, subnet_id=5, confirm=True
                )
