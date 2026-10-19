import pytest
import respx
from httpx import Response

from maasmcp.config import MaasmcpConfig
from maasmcp.curated.create_interface_vlan import CreateInterfaceVlanTool
from maasmcp.maas.client import MaasClient


async def test_create_interface_vlan_happy(monkeypatch):
    """Caller passes IEEE VID (79); the tool translates to MAAS internal id
    (5001) via list_subnets and posts the body with parent + vlan (internal).
    Pre-condition auto-fix: PUT on the parent to set its untagged VLAN before
    op-create_vlan (otherwise MAAS 500s — see memory maas-create-vlan-requires-parent-vlan)."""
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    subnets_payload = [
        {"id": 1, "vlan": {"vid": 79, "id": 5001}},
        {"id": 2, "vlan": {"vid": 115, "id": 5002}},
    ]
    with respx.mock(base_url=maas_client.base_url) as mock:
        mock.get("/api/2.0/subnets/").mock(return_value=Response(200, json=subnets_payload))
        parent_put = mock.put("/api/2.0/nodes/abc123/interfaces/8/").mock(
            return_value=Response(200, json={"id": 8, "vlan_id": 5001})
        )
        route = mock.post("/api/2.0/nodes/abc123/interfaces/op-create_vlan").mock(
            return_value=Response(200, json={"id": 40, "vlan_id": 5001, "type": "vlan"})
        )
        async with maas_client:
            result = await CreateInterfaceVlanTool().run(
                maas_client, system_id="abc123", parent_id=8, vid=79, confirm=True
            )
    assert result == {"id": 40, "vlan_id": 5001, "type": "vlan"}
    assert route.called
    assert parent_put.called
    parent_body = parent_put.calls.last.request.read().decode()
    assert 'name="vlan"' in parent_body
    assert "5001" in parent_body
    sent_body = route.calls.last.request.read().decode()
    assert 'name="parent"' in sent_body
    assert "8" in sent_body
    assert 'name="vlan"' in sent_body
    assert "5001" in sent_body


async def test_create_interface_vlan_collection_level_url(monkeypatch):
    """The path must NOT contain a parent iface id segment — MAAS exposes
    op-create_vlan at the collection level."""
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url, assert_all_called=False) as mock:
        mock.get("/api/2.0/subnets/").mock(
            return_value=Response(200, json=[{"id": 1, "vlan": {"vid": 79, "id": 5001}}])
        )
        # Pre-condition auto-fix PUT is allowed but not asserted here.
        mock.put("/api/2.0/nodes/abc123/interfaces/8/").mock(
            return_value=Response(200, json={"id": 8})
        )
        item_route = mock.post("/api/2.0/nodes/abc123/interfaces/8/op-create_vlan").mock(
            return_value=Response(200, json={"id": 40})
        )
        coll_route = mock.post("/api/2.0/nodes/abc123/interfaces/op-create_vlan").mock(
            return_value=Response(200, json={"id": 40})
        )
        async with maas_client:
            await CreateInterfaceVlanTool().run(
                maas_client, system_id="abc123", parent_id=8, vid=79, confirm=True
            )
    assert coll_route.called
    assert not item_route.called


async def test_create_interface_vlan_requires_confirm(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    async with maas_client:
        with pytest.raises(ValueError, match="confirm=True"):
            await CreateInterfaceVlanTool().run(
                maas_client, system_id="abc123", parent_id=8, vid=100, confirm=False
            )


async def test_create_interface_vlan_invalid_vlan(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    async with maas_client:
        with pytest.raises(ValueError, match="vid"):
            await CreateInterfaceVlanTool().run(
                maas_client, system_id="abc123", parent_id=8, vid=0, confirm=True
            )


async def test_create_interface_vlan_unknown_vid_raises(monkeypatch):
    """If no subnet exists on the requested VID, the translator must raise."""
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
                await CreateInterfaceVlanTool().run(
                    maas_client, system_id="abc123", parent_id=8, vid=4242, confirm=True
                )


async def test_create_interface_vlan_non_dict_raises(monkeypatch):
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
        # Auto-fix PUT is allowed but mocked silently.
        mock.put("/api/2.0/nodes/abc123/interfaces/8/").mock(
            return_value=Response(200, json={"id": 8})
        )
        mock.post("/api/2.0/nodes/abc123/interfaces/op-create_vlan").mock(
            return_value=Response(200, json="bad")
        )
        async with maas_client:
            with pytest.raises(ValueError, match="non-dict"):
                await CreateInterfaceVlanTool().run(
                    maas_client, system_id="abc123", parent_id=8, vid=79, confirm=True
                )


async def test_create_interface_vlan_auto_fixes_parent_vlan(monkeypatch):
    """The pre-condition auto-fix: when the parent's untagged VLAN is unset,
    op-create_vlan returns 500 from MAAS. The tool must PUT the parent's
    untagged VLAN first so the post succeeds transparently. This test
    simulates the original failure mode (parent vlan=null → op 500s) and
    confirms the tool's PUT call prevents it."""
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
        # Track call order: PUT on parent must happen BEFORE POST op-create_vlan.
        call_order: list[str] = []

        def _put_handler(request):
            call_order.append("put_parent_vlan")
            return Response(200, json={"id": 8, "vlan_id": 5001})

        def _post_handler(request):
            call_order.append("post_op_create_vlan")
            return Response(200, json={"id": 40, "type": "vlan", "vlan_id": 5001})

        mock.put("/api/2.0/nodes/abc123/interfaces/8/").mock(side_effect=_put_handler)
        mock.post("/api/2.0/nodes/abc123/interfaces/op-create_vlan").mock(side_effect=_post_handler)
        async with maas_client:
            result = await CreateInterfaceVlanTool().run(
                maas_client, system_id="abc123", parent_id=8, vid=79, confirm=True
            )
    assert result["id"] == 40
    assert call_order == ["put_parent_vlan", "post_op_create_vlan"]


async def test_create_interface_vlan_409_propagates(monkeypatch):
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
        # Auto-fix PUT is allowed but mocked silently.
        mock.put("/api/2.0/nodes/abc123/interfaces/8/").mock(
            return_value=Response(200, json={"id": 8})
        )
        mock.post("/api/2.0/nodes/abc123/interfaces/op-create_vlan").mock(
            return_value=Response(409, text="dup")
        )
        async with maas_client:
            with pytest.raises(Exception) as exc_info:
                await CreateInterfaceVlanTool().run(
                    maas_client, system_id="abc123", parent_id=8, vid=79, confirm=True
                )
    assert "409" in str(exc_info.value)


def test_name_confusion_paths_differ():
    """Cluster-level create_vlan uses /fabrics/{fid}/vlans/; nested
    create_interface_vlan uses /nodes/{sid}/interfaces/op-create_vlan
    (collection level)."""
    from maasmcp.curated._network_paths import (
        interfaces_collection_op_path,
        vlan_path,
        vlans_path,
    )

    assert vlans_path(1) == "/api/2.0/fabrics/1/vlans/"
    assert vlan_path(1, 5) == "/api/2.0/fabrics/1/vlans/5/"
    assert (
        interfaces_collection_op_path("abc", "op-create_vlan")
        == "/api/2.0/nodes/abc/interfaces/op-create_vlan"
    )
    assert not vlans_path(1).startswith("/nodes/")
    assert not interfaces_collection_op_path("abc", "op-create_vlan").startswith("/vlans/")
