import pytest
import respx
from httpx import Response

from maasmcp.config import MaasmcpConfig
from maasmcp.curated.create_bridge import CreateBridgeTool
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


def _stub_link_probe(mock, system_id, bridge_id, member_links):
    """Stub the post-create GET on the bridge + each member.

    member_links is a list of (member_id, link_connected) tuples.
    """
    mock.get(f"/api/2.0/nodes/{system_id}/interfaces/{bridge_id}/").mock(
        return_value=Response(200, json={"id": bridge_id, "link_connected": True})
    )
    for mid, link_up in member_links:
        mock.get(f"/api/2.0/nodes/{system_id}/interfaces/{mid}/").mock(
            return_value=Response(200, json={"id": mid, "link_connected": link_up})
        )


async def test_create_bridge_happy(monkeypatch):
    maas_client = _client(monkeypatch)
    with respx.mock(base_url=maas_client.base_url) as mock:
        route = mock.post("/api/2.0/nodes/abc123/interfaces/op-create_bridge").mock(
            return_value=Response(200, json={"id": 31, "name": "br0", "type": "bridge"})
        )
        _stub_link_probe(mock, "abc123", 31, [(9, True)])
        async with maas_client:
            result = await CreateBridgeTool().run(
                maas_client, system_id="abc123", name="br0", members=[9], confirm=True
            )
    assert result["id"] == 31
    assert result["name"] == "br0"
    assert result["type"] == "bridge"
    # New augmented fields:
    assert result["link_state_classification"] == "bond_up_members_up"
    assert result["member_link_states"] == [
        {"id": 9, "name": None, "link_connected": True},
    ]
    assert route.called


async def test_create_bridge_sends_singular_parent_part(monkeypatch):
    """MAAS takes a single 'parent' field, not repeated 'parents' parts."""
    maas_client = _client(monkeypatch)
    with respx.mock(base_url=maas_client.base_url) as mock:
        route = mock.post("/api/2.0/nodes/abc123/interfaces/op-create_bridge").mock(
            return_value=Response(200, json={"id": 31})
        )
        _stub_link_probe(mock, "abc123", 31, [(9, True)])
        async with maas_client:
            await CreateBridgeTool().run(
                maas_client, system_id="abc123", name="br0", members=[9], confirm=True
            )
    sent_body = route.calls.last.request.read().decode()
    assert 'name="parent"' in sent_body
    assert 'name="parents"' not in sent_body


async def test_create_bridge_rejects_multiple_members(monkeypatch):
    """MAAS's bridge model has a single parent — >1 member is a client error."""
    maas_client = _client(monkeypatch)
    with respx.mock(base_url=maas_client.base_url) as mock:
        async with maas_client:
            with pytest.raises(ValueError, match="single parent"):
                await CreateBridgeTool().run(
                    maas_client, system_id="abc123", name="br0", members=[9, 10], confirm=True
                )
    assert not mock.calls


async def test_create_bridge_requires_confirm(monkeypatch):
    maas_client = _client(monkeypatch)
    with respx.mock(base_url=maas_client.base_url) as mock:
        async with maas_client:
            with pytest.raises(ValueError, match="confirm=True"):
                await CreateBridgeTool().run(
                    maas_client, system_id="abc123", name="br0", members=[9], confirm=False
                )
    assert not mock.calls


async def test_create_bridge_empty_members_raises(monkeypatch):
    maas_client = _client(monkeypatch)
    async with maas_client:
        with pytest.raises(ValueError, match="at least one member"):
            await CreateBridgeTool().run(
                maas_client, system_id="abc123", name="br0", members=[], confirm=True
            )


async def test_create_bridge_non_dict_raises(monkeypatch):
    maas_client = _client(monkeypatch)
    with respx.mock(base_url=maas_client.base_url) as mock:
        mock.post("/api/2.0/nodes/abc123/interfaces/op-create_bridge").mock(
            return_value=Response(200, json="bad")
        )
        async with maas_client:
            with pytest.raises(ValueError, match="non-dict"):
                await CreateBridgeTool().run(
                    maas_client, system_id="abc123", name="br0", members=[9], confirm=True
                )


async def test_create_bridge_409_propagates(monkeypatch):
    maas_client = _client(monkeypatch)
    with respx.mock(base_url=maas_client.base_url) as mock:
        mock.post("/api/2.0/nodes/abc123/interfaces/op-create_bridge").mock(
            return_value=Response(409, text="dup")
        )
        async with maas_client:
            with pytest.raises(Exception) as exc_info:
                await CreateBridgeTool().run(
                    maas_client, system_id="abc123", name="br0", members=[9], confirm=True
                )
    assert "409" in str(exc_info.value)


async def test_create_bridge_classifies_member_suppression(monkeypatch):
    """The bridge edge case: bridge up, member down (slave suppression)."""
    maas_client = _client(monkeypatch)
    with respx.mock(base_url=maas_client.base_url) as mock:
        mock.post("/api/2.0/nodes/abc123/interfaces/op-create_bridge").mock(
            return_value=Response(
                200,
                json={"id": 31, "name": "br0", "link_connected": True},
            )
        )
        mock.get("/api/2.0/nodes/abc123/interfaces/31/").mock(
            return_value=Response(200, json={"id": 31, "name": "br0", "link_connected": True})
        )
        mock.get("/api/2.0/nodes/abc123/interfaces/9/").mock(
            return_value=Response(200, json={"id": 9, "name": "eth9", "link_connected": False})
        )
        async with maas_client:
            result = await CreateBridgeTool().run(
                maas_client, system_id="abc123", name="br0", members=[9], confirm=True
            )
    assert result["link_state_classification"] == "bond_up_members_down"
    assert result["member_link_states"] == [
        {"id": 9, "name": "eth9", "link_connected": False},
    ]


async def test_create_bridge_classifies_physical_fault(monkeypatch):
    """Bridge down AND member down — real physical-layer fault."""
    maas_client = _client(monkeypatch)
    with respx.mock(base_url=maas_client.base_url) as mock:
        mock.post("/api/2.0/nodes/abc123/interfaces/op-create_bridge").mock(
            return_value=Response(200, json={"id": 31, "name": "br0"})
        )
        mock.get("/api/2.0/nodes/abc123/interfaces/31/").mock(
            return_value=Response(200, json={"id": 31, "name": "br0", "link_connected": False})
        )
        mock.get("/api/2.0/nodes/abc123/interfaces/9/").mock(
            return_value=Response(200, json={"id": 9, "name": "eth9", "link_connected": False})
        )
        async with maas_client:
            result = await CreateBridgeTool().run(
                maas_client, system_id="abc123", name="br0", members=[9], confirm=True
            )
    assert result["link_state_classification"] == "bond_down_members_down"


async def test_create_bridge_probe_failure_does_not_raise(monkeypatch):
    """If the post-create GET fails, the create itself still succeeded —
    we must not raise; we annotate with classification='unknown'."""
    maas_client = _client(monkeypatch)
    with respx.mock(base_url=maas_client.base_url) as mock:
        mock.post("/api/2.0/nodes/abc123/interfaces/op-create_bridge").mock(
            return_value=Response(200, json={"id": 31, "name": "br0"})
        )
        mock.get("/api/2.0/nodes/abc123/interfaces/31/").mock(
            return_value=Response(500, text="boom")
        )
        mock.get("/api/2.0/nodes/abc123/interfaces/9/").mock(
            return_value=Response(500, text="boom")
        )
        async with maas_client:
            # No exception expected.
            result = await CreateBridgeTool().run(
                maas_client, system_id="abc123", name="br0", members=[9], confirm=True
            )
    assert result["id"] == 31
    assert result["name"] == "br0"
    assert result["link_state_classification"] == "unknown"
    assert result["member_link_states"] == []
