import pytest
import respx
from httpx import Response

from maasmcp.config import MaasmcpConfig
from maasmcp.curated.update_interface import UpdateInterfaceTool
from maasmcp.maas.client import MaasClient

pytestmark = pytest.mark.asyncio


async def test_update_interface_link_state_for_lacp_member(monkeypatch):
    """The motivating use case: pre-mark LACP bond members as 10G/connected."""
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url, assert_all_called=False) as mock:
        route = mock.put("/api/2.0/nodes/abc123/interfaces/17/").mock(
            return_value=Response(
                200,
                json={
                    "id": 17,
                    "name": "ens7f0np0",
                    "link_connected": True,
                    "link_speed": 10000,
                    "interface_speed": 10000,
                },
            )
        )
        async with maas_client:
            result = await UpdateInterfaceTool().run(
                maas_client,
                system_id="abc123",
                iface_id=17,
                link_connected=True,
                link_speed=10000,
                interface_speed=10000,
                confirm=True,
            )
    assert result["link_connected"] is True
    assert result["link_speed"] == 10000
    assert route.called
    sent = route.calls.last.request.read().decode()
    assert 'name="link_connected"' in sent
    assert "true" in sent
    assert 'name="link_speed"' in sent
    assert "10000" in sent
    assert 'name="interface_speed"' in sent


async def test_update_interface_vlan_clears_with_empty_string(monkeypatch):
    """Per MAAS quirk: vid="" (empty string) clears the untagged VLAN.
    Sending vlan=null in the wire body returns 400."""
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url, assert_all_called=False) as mock:
        route = mock.put("/api/2.0/nodes/abc123/interfaces/17/").mock(
            return_value=Response(200, json={"id": 17, "vlan": None})
        )
        async with maas_client:
            await UpdateInterfaceTool().run(
                maas_client,
                system_id="abc123",
                iface_id=17,
                vid="",
                confirm=True,
            )
    assert route.called
    sent = route.calls.last.request.read().decode()
    # Wire body must contain `vlan=""` (empty), not `vlan=null`.
    assert 'name="vlan"\r\n\r\n' in sent
    assert "null" not in sent.lower()


async def test_update_interface_vlan_translates_vid(monkeypatch):
    """vid=79 (IEEE VID) must translate to MAAS internal id (5001) before PUT."""
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    subnets_payload = [
        {"id": 1, "vlan": {"vid": 79, "id": 5001}},
    ]
    with respx.mock(base_url=maas_client.base_url, assert_all_called=False) as mock:
        mock.get("/api/2.0/subnets/").mock(return_value=Response(200, json=subnets_payload))
        route = mock.put("/api/2.0/nodes/abc123/interfaces/8/").mock(
            return_value=Response(200, json={"id": 8, "vlan_id": 5001})
        )
        async with maas_client:
            result = await UpdateInterfaceTool().run(
                maas_client,
                system_id="abc123",
                iface_id=8,
                vid=79,
                confirm=True,
            )
    assert result == {"id": 8, "vlan_id": 5001}
    sent = route.calls.last.request.read().decode()
    assert 'name="vlan"' in sent
    assert "5001" in sent
    # VID (79) must not leak into the wire body
    assert "vlan=79" not in sent
    assert 'vlan"\r\n\r\n79' not in sent


async def test_update_interface_vlan_rejects_non_empty_string(monkeypatch):
    """vid="foo" is invalid — only the empty string is accepted as a clear."""
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    async with maas_client:
        with pytest.raises(ValueError, match="empty string"):
            await UpdateInterfaceTool().run(
                maas_client,
                system_id="abc123",
                iface_id=8,
                vid="notavalid",
                confirm=True,
            )


async def test_update_interface_requires_confirm(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    async with maas_client:
        with pytest.raises(ValueError, match="confirm=True"):
            await UpdateInterfaceTool().run(
                maas_client,
                system_id="abc123",
                iface_id=8,
                link_connected=True,
                confirm=False,
            )


async def test_update_interface_no_fields_raises(monkeypatch):
    """Calling with all-None kwargs is a no-op — refuse before any MAAS call."""
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url, assert_all_called=False) as mock:
        route = mock.put("/api/2.0/nodes/abc123/interfaces/8/").mock(
            return_value=Response(200, json={"id": 8})
        )
        async with maas_client:
            with pytest.raises(ValueError, match="at least one field"):
                await UpdateInterfaceTool().run(
                    maas_client,
                    system_id="abc123",
                    iface_id=8,
                    confirm=True,
                )
    assert not route.called


async def test_update_interface_rejects_vlan_zero(monkeypatch):
    """vid=0 must raise before any MAAS call (no pre-call hit)."""
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url, assert_all_called=False) as mock:
        route = mock.put("/api/2.0/nodes/abc123/interfaces/8/").mock(
            return_value=Response(200, json={"id": 8})
        )
        async with maas_client:
            with pytest.raises(ValueError, match="vid"):
                await UpdateInterfaceTool().run(
                    maas_client,
                    system_id="abc123",
                    iface_id=8,
                    vid=0,
                    confirm=True,
                )
    assert not route.called


async def test_update_interface_non_dict_raises(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url, assert_all_called=False) as mock:
        mock.put("/api/2.0/nodes/abc123/interfaces/8/").mock(return_value=Response(200, json="bad"))
        async with maas_client:
            with pytest.raises(ValueError, match="non-dict"):
                await UpdateInterfaceTool().run(
                    maas_client,
                    system_id="abc123",
                    iface_id=8,
                    link_connected=True,
                    confirm=True,
                )


async def test_update_interface_only_sends_changed_fields(monkeypatch):
    """Only kwargs that aren't None go into the wire body."""
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url, assert_all_called=False) as mock:
        route = mock.put("/api/2.0/nodes/abc123/interfaces/8/").mock(
            return_value=Response(200, json={"id": 8, "name": "renamed"})
        )
        async with maas_client:
            await UpdateInterfaceTool().run(
                maas_client,
                system_id="abc123",
                iface_id=8,
                name="renamed",
                confirm=True,
            )
    sent = route.calls.last.request.read().decode()
    assert 'name="name"' in sent
    assert "renamed" in sent
    # Untouched fields must not appear
    assert "link_connected" not in sent
    assert "link_speed" not in sent
    assert "vlan" not in sent
