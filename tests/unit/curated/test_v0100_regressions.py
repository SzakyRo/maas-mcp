"""Regression tests for v0.10.0 doc-audit behavior changes.

Each test pins a fix against the vendored MAAS API doc (docs/reference/maasapi.md):
- create_partition: size optional (omitted = all available space), uuid param
- deploy_machine: user_data base64-encoded before the wire
- release_machine: force param forwarded
- power_control: stop_mode/comment on power_off, comment on power_on
- link_subnet: force + default_gateway mode validation
- machines_accept / machines_create: repeated same-name multipart parts
- machine_delete / delete_subnet: force as query param
- update_vlan: DHCP params pass-through, vid 0 = default VLAN
- get_machine: all-hex hostname falls back to ?hostname= lookup on 404
"""

from __future__ import annotations

import base64

import pytest
import respx
from httpx import Response

from maasmcp.config import MaasmcpConfig
from maasmcp.curated.create_partition import CreatePartitionTool
from maasmcp.curated.delete_subnet import DeleteSubnetTool
from maasmcp.curated.deploy_machine import DeployMachineTool
from maasmcp.curated.get_machine import GetMachineTool
from maasmcp.curated.link_subnet import LinkSubnetTool
from maasmcp.curated.machine_delete import MachineDeleteTool
from maasmcp.curated.machines_accept import MachinesAcceptTool
from maasmcp.curated.machines_create import MachinesCreateTool
from maasmcp.curated.power_control import PowerControlTool
from maasmcp.curated.release_machine import ReleaseMachineTool
from maasmcp.curated.update_vlan import UpdateVlanTool
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


async def test_create_partition_omitted_size_uses_available_space(monkeypatch):
    maas_client = _client(monkeypatch)
    with respx.mock(base_url=maas_client.base_url) as mock:
        route = mock.post("/api/2.0/nodes/abc/blockdevices/1/partitions/").mock(
            return_value=Response(200, json={"id": 7})
        )
        async with maas_client:
            result = await CreatePartitionTool().run(
                maas_client, system_id="abc", block_device_id=1, confirm=True
            )
    assert route.called
    assert result == {"id": 7}
    body = route.calls.last.request.content.decode(errors="replace")
    assert 'name="size"' not in body


async def test_create_partition_uuid_reaches_wire(monkeypatch):
    maas_client = _client(monkeypatch)
    with respx.mock(base_url=maas_client.base_url) as mock:
        route = mock.post("/api/2.0/nodes/abc/blockdevices/1/partitions/").mock(
            return_value=Response(200, json={"id": 7})
        )
        async with maas_client:
            await CreatePartitionTool().run(
                maas_client,
                system_id="abc",
                block_device_id=1,
                size="100G",
                uuid="01234567-89ab-cdef-0123-456789abcdef",
                confirm=True,
            )
    body = route.calls.last.request.content.decode(errors="replace")
    assert 'name="uuid"' in body
    assert 'name="size"' in body


async def test_deploy_machine_base64_encodes_user_data(monkeypatch):
    maas_client = _client(monkeypatch)
    raw = "#cloud-config\npackages:\n  - nginx\n"
    with respx.mock(base_url=maas_client.base_url) as mock:
        # Pre-flight GET: machine already commissioned -> no commission step.
        # Post-deploy polls flip status_name to Deployed.
        mock.get("/api/2.0/machines/abc/").mock(
            side_effect=[
                Response(
                    200,
                    json={
                        "status_name": "Allocated",
                        "commissioning_status_name": "Passed",
                        "system_id": "abc",
                    },
                ),
                Response(200, json={"system_id": "abc", "status_name": "Deployed"}),
            ]
        )
        route = mock.post("/api/2.0/machines/abc/op-deploy").mock(return_value=Response(200))
        async with maas_client:
            result = await DeployMachineTool().run(
                maas_client,
                system_id="abc",
                distro="ubuntu/jammy",
                user_data=raw,
                confirm=True,
            )
    assert result["status_name"] == "Deployed"
    body = route.calls.last.request.content.decode(errors="replace")
    assert base64.b64encode(raw.encode()).decode() in body
    assert "#cloud-config" not in body


async def test_release_machine_force_forwarded(monkeypatch):
    maas_client = _client(monkeypatch)
    with respx.mock(base_url=maas_client.base_url) as mock:
        route = mock.post("/api/2.0/machines/abc/op-release").mock(return_value=Response(204))
        async with maas_client:
            await ReleaseMachineTool().run(maas_client, system_id="abc", force=True, confirm=True)
    body = route.calls.last.request.content.decode(errors="replace")
    assert 'name="force"' in body


async def test_power_control_soft_stop_mode_body(monkeypatch):
    maas_client = _client(monkeypatch)
    with respx.mock(base_url=maas_client.base_url) as mock:
        mock.get("/api/2.0/machines/abc/").mock(
            return_value=Response(200, json={"status_name": "Ready"})
        )
        route = mock.post("/api/2.0/machines/abc/op-power_off").mock(return_value=Response(204))
        async with maas_client:
            await PowerControlTool().run(
                maas_client,
                system_id="abc",
                action="off",
                stop_mode="soft",
                comment="maintenance window",
                confirm=True,
            )
    body = route.calls.last.request.content.decode(errors="replace")
    assert 'name="stop_mode"' in body and "soft" in body
    assert 'name="comment"' in body and "maintenance" in body


async def test_power_control_bad_stop_mode_rejected(monkeypatch):
    maas_client = _client(monkeypatch)
    with respx.mock(base_url=maas_client.base_url) as mock:
        async with maas_client:
            with pytest.raises(ValueError, match="stop_mode"):
                await PowerControlTool().run(
                    maas_client, system_id="abc", action="off", stop_mode="warm", confirm=True
                )
    assert not mock.calls


async def test_link_subnet_force_and_default_gateway_mode(monkeypatch):
    maas_client = _client(monkeypatch)
    with respx.mock(base_url=maas_client.base_url) as mock:
        # default_gateway on DHCP must be rejected before any call
        async with maas_client:
            with pytest.raises(ValueError, match="AUTO or STATIC"):
                await LinkSubnetTool().run(
                    maas_client,
                    system_id="abc",
                    iface_id=9,
                    subnet_id=1,
                    mode="DHCP",
                    default_gateway=True,
                    confirm=True,
                )
        assert not mock.calls
        route = mock.post("/api/2.0/nodes/abc/interfaces/9/op-link_subnet").mock(
            return_value=Response(200, json={"id": 9})
        )
        async with maas_client:
            await LinkSubnetTool().run(
                maas_client,
                system_id="abc",
                iface_id=9,
                subnet_id=1,
                mode="LINK_UP",
                force=True,
                confirm=True,
            )
    body = route.calls.last.request.content.decode(errors="replace")
    assert 'name="force"' in body


async def test_machines_accept_repeats_machines_parts(monkeypatch):
    maas_client = _client(monkeypatch)
    with respx.mock(base_url=maas_client.base_url) as mock:
        route = mock.post("/api/2.0/machines/?op=accept").mock(return_value=Response(200, json={}))
        async with maas_client:
            await MachinesAcceptTool().run(maas_client, machines=["abc", "def"], confirm=True)
    body = route.calls.last.request.content.decode(errors="replace")
    assert body.count('name="machines"') == 2
    assert '["abc", "def"]' not in body


async def test_machines_create_mac_list_repeats_parts(monkeypatch):
    maas_client = _client(monkeypatch)
    with respx.mock(base_url=maas_client.base_url) as mock:
        route = mock.post("/api/2.0/machines/").mock(
            return_value=Response(200, json={"system_id": "new"})
        )
        async with maas_client:
            await MachinesCreateTool().run(
                maas_client,
                architecture="amd64",
                mac_addresses=["00:11:22:33:44:55", "00:11:22:33:44:66"],
                confirm=True,
            )
    body = route.calls.last.request.content.decode(errors="replace")
    assert body.count('name="mac_addresses"') == 2


async def test_machine_delete_force_query_param(monkeypatch):
    maas_client = _client(monkeypatch)
    with respx.mock(base_url=maas_client.base_url) as mock:
        route = mock.delete("/api/2.0/machines/abc/").mock(return_value=Response(204))
        async with maas_client:
            await MachineDeleteTool().run(maas_client, system_id="abc", force=True, confirm=True)
    assert route.called
    assert "force=1" in str(route.calls.last.request.url)


async def test_delete_subnet_force_query_param(monkeypatch):
    maas_client = _client(monkeypatch)
    with respx.mock(base_url=maas_client.base_url) as mock:
        route = mock.delete("/api/2.0/subnets/5/").mock(return_value=Response(204))
        async with maas_client:
            await DeleteSubnetTool().run(maas_client, subnet_id=5, force=True, confirm=True)
    assert route.called
    assert "force=1" in str(route.calls.last.request.url)


async def test_update_vlan_vid_zero_and_dhcp_params(monkeypatch):
    """vid=0 (untagged default VLAN) is valid; DHCP params pass through."""
    maas_client = _client(monkeypatch)
    with respx.mock(base_url=maas_client.base_url) as mock:
        route = mock.put("/api/2.0/fabrics/0/vlans/0/").mock(
            return_value=Response(200, json={"id": 5000, "vid": 0, "dhcp_on": True})
        )
        async with maas_client:
            result = await UpdateVlanTool().run(
                maas_client,
                fabric_id=0,
                vid=0,
                dhcp_on=True,
                primary_rack="xyz789",
                confirm=True,
            )
    assert route.called
    assert result["dhcp_on"] is True
    body = route.calls.last.request.content.decode(errors="replace")
    assert 'name="dhcp_on"' in body and 'name="primary_rack"' in body


async def test_update_vlan_nothing_to_update_rejected(monkeypatch):
    maas_client = _client(monkeypatch)
    with respx.mock(base_url=maas_client.base_url) as mock:
        async with maas_client:
            with pytest.raises(ValueError, match="nothing to update"):
                await UpdateVlanTool().run(maas_client, fabric_id=1, vid=42, confirm=True)
    assert not mock.calls


async def test_get_machine_hex_hostname_falls_back_on_404(monkeypatch):
    maas_client = _client(monkeypatch)
    with respx.mock(base_url=maas_client.base_url) as mock:
        mock.get("/api/2.0/machines/decaf0/").mock(return_value=Response(404))
        route = mock.get("/api/2.0/machines/").mock(
            return_value=Response(
                200, json=[{"system_id": "zz1234", "hostname": "decaf0", "power_state": "off"}]
            )
        )
        async with maas_client:
            result = await GetMachineTool().run(maas_client, identifier="decaf0")
    assert route.called
    assert result["system_id"] == "zz1234"
    assert result["hostname"] == "decaf0"


async def test_get_machine_non_hex_system_id_still_resolves(monkeypatch):
    """MAAS system_ids are base-36 — '84t4pa' contains non-hex letters and is
    a perfectly valid system_id; the hostname miss must fall through to a
    direct system_id GET."""
    maas_client = _client(monkeypatch)
    with respx.mock(base_url=maas_client.base_url) as mock:
        mock.get("/api/2.0/machines/", params={"hostname": "84t4pa"}).mock(
            return_value=Response(200, json=[])
        )
        route = mock.get("/api/2.0/machines/84t4pa/").mock(
            return_value=Response(200, json={"system_id": "84t4pa", "hostname": "busy-feline"})
        )
        async with maas_client:
            result = await GetMachineTool().run(maas_client, identifier="84t4pa")
    assert route.called
    assert result["system_id"] == "84t4pa"
