"""Tests for configure_link: one-call repair of a DOWN application link.

Cross-link topology scenario: 4x 10G links (Application UP, Storage UP,
Application DOWN, Storage UP). This tool takes the DOWN application's
iface_id from a prior list_interfaces discovery call and, in one atomic
PUT, sets it connected, 10G, and onto its VLAN — then verifies.
"""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from maasmcp.config import MaasmcpConfig
from maasmcp.curated.configure_link import ConfigureLinkTool
from maasmcp.maas.client import MaasClient

pytestmark = pytest.mark.asyncio

BASE = "https://maas.example.com/MAAS"
IFACE_URL = "/api/2.0/nodes/abc123/interfaces/8/"
SUBNETS_URL = "/api/2.0/subnets/"

DOWN_IFACE = {
    "id": 8,
    "name": "ens7f1np0",
    "type": "physical",
    "link_connected": False,
    "link_speed": 0,
    "interface_speed": 10000,
    "vlan_id": 1,
}

UP_CONFIGURED_IFACE = {
    "id": 8,
    "name": "ens7f1np0",
    "type": "physical",
    "link_connected": True,
    "link_speed": 10000,
    "interface_speed": 10000,
    "vlan_id": 5001,
}

SUBNETS = [{"id": 1, "vlan": {"vid": 79, "id": 5001}}]


def _client(monkeypatch: pytest.MonkeyPatch) -> MaasClient:
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", BASE)
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    return maas_client


async def test_configure_link_happy_path_single_put(monkeypatch):
    """Connect + 10G + VLAN land in ONE atomic PUT; final state verified."""
    maas_client = _client(monkeypatch)
    with respx.mock(base_url=BASE, assert_all_called=False) as mock:
        get_route = mock.get(IFACE_URL).mock(
            side_effect=[Response(200, json=DOWN_IFACE), Response(200, json=UP_CONFIGURED_IFACE)]
        )
        mock.get(SUBNETS_URL).mock(return_value=Response(200, json=SUBNETS))
        put_route = mock.put(IFACE_URL).mock(return_value=Response(200, json=UP_CONFIGURED_IFACE))
        async with maas_client:
            result = await ConfigureLinkTool().run(
                maas_client,
                system_id="abc123",
                iface_id=8,
                vid=79,
                confirm=True,
            )
    assert put_route.call_count == 1
    assert get_route.call_count == 2  # pre-flight + post-flight verify
    sent = put_route.calls.last.request.read().decode()
    # Exact multipart fragment: lowercase "true" must be the link_connected
    # value (client._stringify emits lowercase; MAAS rejects Python "True").
    assert 'name="link_connected"\r\n\r\ntrue' in sent
    assert 'name="link_speed"' in sent and "10000" in sent
    assert 'name="interface_speed"' in sent
    # VID 79 translated to MAAS internal id 5001; raw VID must not leak.
    assert 'name="vlan"' in sent and "5001" in sent
    assert 'vlan"\r\n\r\n79' not in sent
    assert result["changed"] is True
    assert result["verified"] is True
    assert result["previous"]["link_connected"] is False
    assert result["interface"]["vlan_id"] == 5001
    assert result["name"] == "ens7f1np0"


async def test_configure_link_requires_confirm(monkeypatch):
    maas_client = _client(monkeypatch)
    async with maas_client:
        with pytest.raises(ValueError, match="confirm=True"):
            await ConfigureLinkTool().run(
                maas_client,
                system_id="abc123",
                iface_id=8,
                vid=79,
                confirm=False,
            )
    assert not respx.calls


async def test_configure_link_rejects_vid_zero_without_calls(monkeypatch):
    maas_client = _client(monkeypatch)
    with respx.mock(base_url=BASE, assert_all_called=False) as mock:
        route = mock.get(IFACE_URL).mock(return_value=Response(200, json=DOWN_IFACE))
        async with maas_client:
            with pytest.raises(ValueError, match="vid"):
                await ConfigureLinkTool().run(
                    maas_client,
                    system_id="abc123",
                    iface_id=8,
                    vid=0,
                    confirm=True,
                )
    assert not route.called


async def test_configure_link_rejects_non_physical(monkeypatch):
    """Refuse to reconfigure bonds/bridges/vlan-interfaces — physical only."""
    maas_client = _client(monkeypatch)
    with respx.mock(base_url=BASE, assert_all_called=False) as mock:
        mock.get(IFACE_URL).mock(
            return_value=Response(200, json={**DOWN_IFACE, "type": "bond"})
        )
        put_route = mock.put(IFACE_URL).mock(return_value=Response(200, json={}))
        async with maas_client:
            with pytest.raises(ValueError, match="physical"):
                await ConfigureLinkTool().run(
                    maas_client,
                    system_id="abc123",
                    iface_id=8,
                    vid=79,
                    confirm=True,
                )
    assert not put_route.called


async def test_configure_link_custom_speed(monkeypatch):
    maas_client = _client(monkeypatch)
    given = {**UP_CONFIGURED_IFACE, "link_speed": 25000, "interface_speed": 25000}
    with respx.mock(base_url=BASE, assert_all_called=False) as mock:
        mock.get(IFACE_URL).mock(side_effect=[Response(200, json=DOWN_IFACE), Response(200, json=given)])
        mock.get(SUBNETS_URL).mock(return_value=Response(200, json=SUBNETS))
        put_route = mock.put(IFACE_URL).mock(return_value=Response(200, json=given))
        async with maas_client:
            await ConfigureLinkTool().run(
                maas_client,
                system_id="abc123",
                iface_id=8,
                vid=79,
                speed_mbps=25000,
                confirm=True,
            )
    sent = put_route.calls.last.request.read().decode()
    assert "25000" in sent
    assert "10000" not in sent


async def test_configure_link_idempotent_noop(monkeypatch):
    """Interface already connected at 10G on the right VLAN → no PUT."""
    maas_client = _client(monkeypatch)
    with respx.mock(base_url=BASE, assert_all_called=False) as mock:
        mock.get(IFACE_URL).mock(return_value=Response(200, json=UP_CONFIGURED_IFACE))
        mock.get(SUBNETS_URL).mock(return_value=Response(200, json=SUBNETS))
        put_route = mock.put(IFACE_URL).mock(return_value=Response(200, json={}))
        async with maas_client:
            result = await ConfigureLinkTool().run(
                maas_client,
                system_id="abc123",
                iface_id=8,
                vid=79,
                confirm=True,
            )
    assert not put_route.called
    assert result["changed"] is False
    assert result["verified"] is True
    assert result["previous"] == {
        "link_connected": True,
        "link_speed": 10000,
        "interface_speed": 10000,
        "vlan_id": 5001,
    }


async def test_configure_link_verified_false_on_drift(monkeypatch):
    """Post-flight GET disagreeing with desired state surfaces verified=False."""
    maas_client = _client(monkeypatch)
    drifted = {**UP_CONFIGURED_IFACE, "link_connected": False}
    with respx.mock(base_url=BASE, assert_all_called=False) as mock:
        mock.get(IFACE_URL).mock(side_effect=[Response(200, json=DOWN_IFACE), Response(200, json=drifted)])
        mock.get(SUBNETS_URL).mock(return_value=Response(200, json=SUBNETS))
        mock.put(IFACE_URL).mock(return_value=Response(200, json=drifted))
        async with maas_client:
            result = await ConfigureLinkTool().run(
                maas_client,
                system_id="abc123",
                iface_id=8,
                vid=79,
                confirm=True,
            )
    assert result["changed"] is True
    assert result["verified"] is False


async def test_configure_link_unknown_vlan_raises(monkeypatch):
    """VID with no subnet → _resolve_vlan_id error, no PUT performed."""
    maas_client = _client(monkeypatch)
    with respx.mock(base_url=BASE, assert_all_called=False) as mock:
        mock.get(IFACE_URL).mock(return_value=Response(200, json=DOWN_IFACE))
        mock.get(SUBNETS_URL).mock(return_value=Response(200, json=[]))
        put_route = mock.put(IFACE_URL).mock(return_value=Response(200, json={}))
        async with maas_client:
            with pytest.raises(ValueError, match="no subnet found on VLAN 99"):
                await ConfigureLinkTool().run(
                    maas_client,
                    system_id="abc123",
                    iface_id=8,
                    vid=99,
                    confirm=True,
                )
    assert not put_route.called


async def test_configure_link_resolves_hostname(monkeypatch):
    """hostname-only addressing goes through /machines/ exact-match lookup."""
    maas_client = _client(monkeypatch)
    with respx.mock(base_url=BASE, assert_all_called=False) as mock:
        machines_route = mock.get("/api/2.0/machines/", params={"hostname": "node-1"}).mock(
            return_value=Response(200, json=[{"system_id": "abc123", "hostname": "node-1"}])
        )
        mock.get(IFACE_URL).mock(return_value=Response(200, json=UP_CONFIGURED_IFACE))
        mock.get(SUBNETS_URL).mock(return_value=Response(200, json=SUBNETS))
        async with maas_client:
            result = await ConfigureLinkTool().run(
                maas_client,
                iface_id=8,
                vid=79,
                hostname="node-1",
                confirm=True,
            )
    assert machines_route.called
    assert result["changed"] is False  # fixture already matches desired state


async def test_configure_link_hostname_system_id_conflict_raises(monkeypatch):
    maas_client = _client(monkeypatch)
    with respx.mock(base_url=BASE, assert_all_called=False) as mock:
        mock.get("/api/2.0/machines/", params={"hostname": "node-1"}).mock(
            return_value=Response(200, json=[{"system_id": "other99", "hostname": "node-1"}])
        )
        put_route = mock.put(IFACE_URL).mock(return_value=Response(200, json={}))
        async with maas_client:
            with pytest.raises(ValueError, match="does not belong to hostname"):
                await ConfigureLinkTool().run(
                    maas_client,
                    system_id="abc123",
                    hostname="node-1",
                    iface_id=8,
                    vid=79,
                    confirm=True,
                )
    assert not put_route.called


async def test_configure_link_post_get_failure_falls_back(monkeypatch):
    """Non-dict post-flight GET → verified=False, interface falls back to PUT echo."""
    maas_client = _client(monkeypatch)
    with respx.mock(base_url=BASE, assert_all_called=False) as mock:
        mock.get(IFACE_URL).mock(
            side_effect=[Response(200, json=DOWN_IFACE), Response(200, json="unexpected")]
        )
        mock.get(SUBNETS_URL).mock(return_value=Response(200, json=SUBNETS))
        mock.put(IFACE_URL).mock(return_value=Response(200, json=UP_CONFIGURED_IFACE))
        async with maas_client:
            result = await ConfigureLinkTool().run(
                maas_client,
                system_id="abc123",
                iface_id=8,
                vid=79,
                confirm=True,
            )
    assert result["changed"] is True
    assert result["verified"] is False
    assert result["interface"] == UP_CONFIGURED_IFACE  # PUT echo fallback
