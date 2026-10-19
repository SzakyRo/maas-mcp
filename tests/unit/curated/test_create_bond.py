import pytest
import respx
from httpx import Response

from maasmcp.config import MaasmcpConfig
from maasmcp.curated.create_bond import CreateBondTool
from maasmcp.maas.client import MaasClient

pytestmark = pytest.mark.asyncio


def _stub_link_probe(mock, system_id, bond_id, member_links):
    """Stub the post-create GET on the bond + each member.

    member_links is a list of (member_id, link_connected) tuples.
    Stubs use link_connected=True by default so the classification comes
    out as bond_up_members_up (benign) for tests that don't exercise the
    classification paths explicitly.
    """
    mock.get(f"/api/2.0/nodes/{system_id}/interfaces/{bond_id}/").mock(
        return_value=Response(200, json={"id": bond_id, "link_connected": True})
    )
    for mid, link_up in member_links:
        mock.get(f"/api/2.0/nodes/{system_id}/interfaces/{mid}/").mock(
            return_value=Response(200, json={"id": mid, "link_connected": link_up})
        )


def _stub_member_pre_mark(mock, system_id, member_ids):
    """Stub the LACP pre-mark PUTs that create_bond issues for each member
    before posting op-create_bond. Without these mocks, respx lets the PUTs
    fall through to the network — slow tests + real-network noise.

    Per memory maas-bond-slave-suppression: this pre-mark is what makes
    the post-create classification useful from the start."""
    for mid in member_ids:
        mock.put(f"/api/2.0/nodes/{system_id}/interfaces/{mid}/").mock(
            return_value=Response(
                200, json={"id": mid, "link_connected": True, "link_speed": 10000}
            )
        )


async def test_create_bond_happy(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url) as mock:
        # Collection-level URL — no iface id in path segment.
        _stub_member_pre_mark(mock, "abc123", [9, 10])
        route = mock.post("/api/2.0/nodes/abc123/interfaces/op-create_bond").mock(
            return_value=Response(200, json={"id": 30, "name": "bond0", "type": "bond"})
        )
        _stub_link_probe(mock, "abc123", 30, [(9, True), (10, True)])
        async with maas_client:
            result = await CreateBondTool().run(
                maas_client,
                system_id="abc123",
                name="bond0",
                bond_mode="802.3ad",
                members=[9, 10],
                confirm=True,
            )
    assert result["id"] == 30
    assert result["name"] == "bond0"
    assert result["type"] == "bond"
    # New augmented fields:
    assert result["link_state_classification"] == "bond_up_members_up"
    assert result["member_link_states"] == [
        {"id": 9, "name": None, "link_connected": True},
        {"id": 10, "name": None, "link_connected": True},
    ]
    assert route.called


async def test_create_bond_sends_repeated_parents_parts(monkeypatch):
    """parents=[9, 10] must produce two multipart parts with the same key name.
    MAAS rejects a stringified list like '[9, 10]'."""
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url) as mock:
        _stub_member_pre_mark(mock, "abc123", [9, 10])
        route = mock.post("/api/2.0/nodes/abc123/interfaces/op-create_bond").mock(
            return_value=Response(200, json={"id": 30})
        )
        _stub_link_probe(mock, "abc123", 30, [(9, True), (10, True)])
        async with maas_client:
            await CreateBondTool().run(
                maas_client,
                system_id="abc123",
                name="bond0",
                bond_mode="802.3ad",
                members=[9, 10],
                confirm=True,
            )
    sent_body = route.calls.last.request.read().decode()
    # Two separate parts (not one stringified list).
    assert sent_body.count('name="parents"') == 2
    assert "9" in sent_body
    assert "10" in sent_body
    # The stringified list form would appear as '[9, 10]' — must NOT.
    assert "[9, 10]" not in sent_body
    assert "[9," not in sent_body


async def test_create_bond_requires_confirm(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    async with maas_client:
        with pytest.raises(ValueError, match="confirm=True"):
            await CreateBondTool().run(
                maas_client,
                system_id="abc123",
                name="bond0",
                bond_mode="802.3ad",
                members=[9],
                confirm=False,
            )


async def test_create_bond_empty_members_raises(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    async with maas_client:
        with pytest.raises(ValueError, match="at least one member"):
            await CreateBondTool().run(
                maas_client,
                system_id="abc123",
                name="bond0",
                bond_mode="802.3ad",
                members=[],
                confirm=True,
            )


async def test_create_bond_non_dict_raises(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url) as mock:
        _stub_member_pre_mark(mock, "abc123", [9])
        mock.post("/api/2.0/nodes/abc123/interfaces/op-create_bond").mock(
            return_value=Response(200, json="bad")
        )
        async with maas_client:
            with pytest.raises(ValueError, match="non-dict"):
                await CreateBondTool().run(
                    maas_client,
                    system_id="abc123",
                    name="bond0",
                    bond_mode="802.3ad",
                    members=[9],
                    confirm=True,
                )


async def test_create_bond_409_propagates(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url) as mock:
        _stub_member_pre_mark(mock, "abc123", [9])
        mock.post("/api/2.0/nodes/abc123/interfaces/op-create_bond").mock(
            return_value=Response(409, text="dup")
        )
        async with maas_client:
            with pytest.raises(Exception) as exc_info:
                await CreateBondTool().run(
                    maas_client,
                    system_id="abc123",
                    name="bond0",
                    bond_mode="802.3ad",
                    members=[9],
                    confirm=True,
                )
    assert "409" in str(exc_info.value)


async def test_create_bond_classifies_lacp_slave_suppression(monkeypatch):
    """The LACP edge case: bond up, members all down (kernel slave suppression).

    The classify step must return 'bond_up_members_down' and surface the
    per-member link state so callers can see at a glance that this is the
    expected pattern, not a physical fault.
    """
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url) as mock:
        _stub_member_pre_mark(mock, "abc123", [9, 10])
        mock.post("/api/2.0/nodes/abc123/interfaces/op-create_bond").mock(
            return_value=Response(
                200,
                json={"id": 30, "name": "bond0", "link_connected": True},
            )
        )
        # Bond itself reports up, but both members report down. This is the
        # LACP slave-suppression signature.
        mock.get("/api/2.0/nodes/abc123/interfaces/30/").mock(
            return_value=Response(200, json={"id": 30, "name": "bond0", "link_connected": True})
        )
        for mid in (9, 10):
            mock.get(f"/api/2.0/nodes/abc123/interfaces/{mid}/").mock(
                return_value=Response(
                    200,
                    json={"id": mid, "name": f"eth{mid}", "link_connected": False},
                )
            )
        async with maas_client:
            result = await CreateBondTool().run(
                maas_client,
                system_id="abc123",
                name="bond0",
                bond_mode="802.3ad",
                members=[9, 10],
                confirm=True,
            )
    assert result["link_state_classification"] == "bond_up_members_down"
    assert result["member_link_states"] == [
        {"id": 9, "name": "eth9", "link_connected": False},
        {"id": 10, "name": "eth10", "link_connected": False},
    ]


async def test_create_bond_classifies_physical_fault(monkeypatch):
    """Bond down AND all members down — real physical-layer fault."""
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url) as mock:
        _stub_member_pre_mark(mock, "abc123", [9, 10])
        mock.post("/api/2.0/nodes/abc123/interfaces/op-create_bond").mock(
            return_value=Response(200, json={"id": 30, "name": "bond0"})
        )
        mock.get("/api/2.0/nodes/abc123/interfaces/30/").mock(
            return_value=Response(200, json={"id": 30, "name": "bond0", "link_connected": False})
        )
        for mid in (9, 10):
            mock.get(f"/api/2.0/nodes/abc123/interfaces/{mid}/").mock(
                return_value=Response(
                    200, json={"id": mid, "name": f"eth{mid}", "link_connected": False}
                )
            )
        async with maas_client:
            result = await CreateBondTool().run(
                maas_client,
                system_id="abc123",
                name="bond0",
                bond_mode="802.3ad",
                members=[9, 10],
                confirm=True,
            )
    assert result["link_state_classification"] == "bond_down_members_down"


async def test_create_bond_probe_failure_does_not_raise(monkeypatch):
    """If the post-create GET fails, the create itself still succeeded —
    we must not raise; we annotate with classification='unknown'."""
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url) as mock:
        _stub_member_pre_mark(mock, "abc123", [9, 10])
        mock.post("/api/2.0/nodes/abc123/interfaces/op-create_bond").mock(
            return_value=Response(200, json={"id": 30, "name": "bond0"})
        )
        # GET on the bond returns 500 — probe fails.
        mock.get("/api/2.0/nodes/abc123/interfaces/30/").mock(
            return_value=Response(500, text="boom")
        )
        for mid in (9, 10):
            mock.get(f"/api/2.0/nodes/abc123/interfaces/{mid}/").mock(
                return_value=Response(500, text="boom")
            )
        async with maas_client:
            # No exception expected.
            result = await CreateBondTool().run(
                maas_client,
                system_id="abc123",
                name="bond0",
                bond_mode="802.3ad",
                members=[9, 10],
                confirm=True,
            )
    # The original create payload is preserved.
    assert result["id"] == 30
    assert result["name"] == "bond0"
    # Classification falls back to 'unknown'.
    assert result["link_state_classification"] == "unknown"
    assert result["member_link_states"] == []


async def test_create_bond_pre_marks_members_as_10g_connected(monkeypatch):
    """LACP pre-mark: PUT on each member with link_connected=True,
    link_speed=10000, interface_speed=10000 BEFORE op-create_bond. This is
    what lets the post-create classification come out as bond_up_members_up
    from the start (avoids the LACP slave-suppression probe loop)."""
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url) as mock:
        # Capture PUT bodies and call order.
        put_calls: list[tuple[str, str]] = []

        def _put_handler(request):
            url = str(request.url)
            body = request.read().decode()
            put_calls.append((url, body))
            return Response(200, json={"id": int(url.rsplit("/", 3)[-2])})

        for mid in (9, 10):
            mock.put(f"/api/2.0/nodes/abc123/interfaces/{mid}/").mock(side_effect=_put_handler)
        post_route = mock.post("/api/2.0/nodes/abc123/interfaces/op-create_bond").mock(
            return_value=Response(200, json={"id": 30, "name": "bond0"})
        )
        _stub_link_probe(mock, "abc123", 30, [(9, True), (10, True)])
        async with maas_client:
            await CreateBondTool().run(
                maas_client,
                system_id="abc123",
                name="bond0",
                bond_mode="802.3ad",
                members=[9, 10],
                confirm=True,
            )
    # Both members pre-marked with 10G/connected, BEFORE the post.
    assert len(put_calls) == 2
    assert put_calls[0][0].endswith("/interfaces/9/")
    assert put_calls[1][0].endswith("/interfaces/10/")
    for _url, body in put_calls:
        assert 'name="link_connected"' in body
        assert "true" in body
        assert 'name="link_speed"' in body
        assert "10000" in body
        assert 'name="interface_speed"' in body
    # Both PUTs must precede the POST.
    assert post_route.called
    # All PUTs recorded before the POST: their recorded URLs reflect this
    # because respx handlers run synchronously; the test would have failed
    # earlier if call ordering was wrong (the second PUT would 404 since
    # the second PUT stub is registered before the POST route).


async def test_create_bond_pre_mark_failure_does_not_block_bond(monkeypatch):
    """Pre-mark PUT failure is best-effort: bond creation must still proceed.
    This covers the case where MAAS rejects the override (e.g. on a deployed
    machine where only name/mac_address can be updated)."""
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url) as mock:
        # Pre-mark PUT fails (e.g. machine is deployed and only name/mac allowed).
        mock.put("/api/2.0/nodes/abc123/interfaces/9/").mock(
            return_value=Response(403, text="forbidden")
        )
        mock.post("/api/2.0/nodes/abc123/interfaces/op-create_bond").mock(
            return_value=Response(200, json={"id": 30, "name": "bond0"})
        )
        _stub_link_probe(mock, "abc123", 30, [(9, True)])
        async with maas_client:
            # Bond creation must succeed despite the pre-mark failure.
            result = await CreateBondTool().run(
                maas_client,
                system_id="abc123",
                name="bond0",
                bond_mode="802.3ad",
                members=[9],
                confirm=True,
            )
    assert result["id"] == 30
    assert result["name"] == "bond0"
