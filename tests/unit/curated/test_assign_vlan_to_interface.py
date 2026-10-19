import pytest
import respx
from httpx import Response

from maasmcp.config import MaasmcpConfig
from maasmcp.curated.assign_vlan_to_interface import AssignVlanToInterfaceTool
from maasmcp.maas.client import MaasClient

pytestmark = pytest.mark.asyncio


async def test_assign_vlan_to_interface_happy(monkeypatch):
    """Caller passes IEEE VID (79); tool translates to MAAS internal id
    (5001) before sending. MAAS 3.7.2 returns 400 if given the VID directly."""
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    subnets_payload = [
        {"id": 1, "vlan": {"vid": 79, "id": 5001}},
    ]
    with respx.mock(base_url=maas_client.base_url) as mock:
        mock.get("/api/2.0/subnets/").mock(return_value=Response(200, json=subnets_payload))
        route = mock.put("/api/2.0/nodes/abc123/interfaces/8/").mock(
            return_value=Response(200, json={"id": 8, "vlan_id": 5001})
        )
        async with maas_client:
            result = await AssignVlanToInterfaceTool().run(
                maas_client, system_id="abc123", iface_id=8, vid=79, confirm=True
            )
    assert result == {"id": 8, "vlan_id": 5001}
    assert route.called
    sent_body = route.calls.last.request.read().decode()
    assert 'name="vlan"' in sent_body
    assert "5001" in sent_body
    assert "vlan=79" not in sent_body
    assert 'vlan"\r\n\r\n79' not in sent_body


async def test_assign_vlan_to_interface_requires_confirm(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    async with maas_client:
        with pytest.raises(ValueError, match="hostname="):
            await AssignVlanToInterfaceTool().run(
                maas_client, system_id="abc123", iface_id=8, vid=100, confirm=False
            )


async def test_assign_vlan_to_interface_invalid_iface_id(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    async with maas_client:
        with pytest.raises(ValueError, match="iface_id"):
            await AssignVlanToInterfaceTool().run(
                maas_client, system_id="abc123", iface_id=0, vid=100, confirm=True
            )


async def test_assign_vlan_to_interface_rejects_vlan_zero(monkeypatch):
    """vid=0 must raise before any MAAS call (no pre-call hit)."""
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url, assert_all_called=False) as mock:
        route = mock.put("/api/2.0/nodes/abc123/interfaces/8/").mock(
            return_value=Response(200, json={"id": 8, "vlan_id": 0})
        )
        async with maas_client:
            with pytest.raises(ValueError, match="vid"):
                await AssignVlanToInterfaceTool().run(
                    maas_client, system_id="abc123", iface_id=8, vid=0, confirm=True
                )
    assert not route.called


async def test_assign_vlan_to_interface_unknown_vid_raises(monkeypatch):
    """If no subnet exists on the requested VID, raise cleanly."""
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url) as mock:
        mock.get("/api/2.0/subnets/").mock(
            return_value=Response(200, json=[{"id": 1, "vlan": {"vid": 79, "id": 5001}}])
        )
        async with maas_client:
            with pytest.raises(ValueError, match="no subnet found on VLAN 4242"):
                await AssignVlanToInterfaceTool().run(
                    maas_client, system_id="abc123", iface_id=8, vid=4242, confirm=True
                )


async def test_assign_vlan_to_interface_non_dict_raises(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url) as mock:
        mock.get("/api/2.0/subnets/").mock(
            return_value=Response(200, json=[{"id": 1, "vlan": {"vid": 79, "id": 5001}}])
        )
        mock.put("/api/2.0/nodes/abc123/interfaces/8/").mock(return_value=Response(200, json="bad"))
        async with maas_client:
            with pytest.raises(ValueError, match="non-dict"):
                await AssignVlanToInterfaceTool().run(
                    maas_client, system_id="abc123", iface_id=8, vid=79, confirm=True
                )
