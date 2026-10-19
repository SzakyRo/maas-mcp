"""Tests for the curated overlay (part 1)."""

from __future__ import annotations

import httpx
import pytest
import respx

from maasmcp.config import MaasConfig
from maasmcp.curated.acquire_machine import AcquireMachineTool
from maasmcp.curated.deploy_machine import DeployMachineTool
from maasmcp.curated.find_available_machines import FindAvailableMachinesTool
from maasmcp.curated.get_machine import GetMachineTool
from maasmcp.curated.list_machines import ListMachinesTool
from maasmcp.curated.power_control import PowerControlTool
from maasmcp.curated.power_status import PowerStatusTool
from maasmcp.curated.release_machine import ReleaseMachineTool
from maasmcp.curated.summary import SummaryTool
from maasmcp.curated.tag_machine import TagMachineTool
from maasmcp.curated.untag_machine import UntagMachineTool
from maasmcp.curated.wait_for_state import WaitForStateTool
from maasmcp.maas.client import MaasClient


def _cfg() -> MaasConfig:
    return MaasConfig(base_url="https://maas.example.com/MAAS", api_key="k")


@pytest.mark.asyncio
@respx.mock
async def test_acquire_machine_finds_and_allocates() -> None:
    respx.get("https://maas.example.com/MAAS/api/2.0/machines/").mock(
        return_value=httpx.Response(
            200,
            json=[
                # Real MAAS shape: status is int enum, status_name is Title-case string.
                {"system_id": "abc", "hostname": "node-1", "status": 5, "status_name": "Ready"},
                {"system_id": "def", "hostname": "node-2", "status": 6, "status_name": "Deployed"},
            ],
        )
    )
    route = respx.post("https://maas.example.com/MAAS/api/2.0/machines/?op=allocate").mock(
        return_value=httpx.Response(200, json={"system_id": "abc"})
    )
    async with MaasClient(_cfg()) as client:
        tool = AcquireMachineTool()
        result = await tool.run(client, hostname="node-1", confirm=True)
    assert result == {"system_id": "abc", "hostname": "node-1", "status_name": "Ready"}
    assert route.call_count == 1
    # Regression guard: the fix must NOT pass ?status=... to MAAS.
    sent_url = str(route.calls.last.request.url)
    assert "status=" not in sent_url, f"unexpected query string in {sent_url}"


@pytest.mark.asyncio
@respx.mock
async def test_acquire_machine_raises_when_no_match() -> None:
    """Empty list response means no machine matches — raise instead of allocating."""
    respx.get("https://maas.example.com/MAAS/api/2.0/machines/").mock(
        return_value=httpx.Response(200, json=[])
    )
    async with MaasClient(_cfg()) as client:
        with pytest.raises(ValueError):
            await AcquireMachineTool().run(client, hostname="ghost", confirm=True)


@pytest.mark.asyncio
@respx.mock
async def test_acquire_machine_requires_confirm() -> None:
    """Allocation is a fleet-level state change — confirm=False raises before any HTTP call."""
    async with MaasClient(_cfg()) as client:
        with pytest.raises(ValueError, match="confirm=True"):
            await AcquireMachineTool().run(client, hostname="node-1", confirm=False)
    assert not respx.calls


@pytest.mark.asyncio
@respx.mock
async def test_acquire_machine_paginates_past_page_1() -> None:
    """Wiring regression: acquire walks all pages. A machine only present on
    page 2 must still be found (pre-0.7.1 a single-page GET missed it)."""
    page1 = [
        {"system_id": f"f{i:03}", "hostname": f"other-{i}", "status_name": "Ready"}
        for i in range(200)
    ]
    page2 = [{"system_id": "zzz999", "hostname": "node-2", "status_name": "Ready"}]
    get_route = respx.get("https://maas.example.com/MAAS/api/2.0/machines/").mock(
        side_effect=[
            httpx.Response(200, json=page1),
            httpx.Response(200, json=page2),
        ]
    )
    post_route = respx.post("https://maas.example.com/MAAS/api/2.0/machines/?op=allocate").mock(
        return_value=httpx.Response(200, json={"system_id": "zzz999"})
    )
    async with MaasClient(_cfg()) as client:
        result = await AcquireMachineTool().run(client, hostname="node-2", confirm=True)
    assert result["system_id"] == "zzz999"
    assert get_route.call_count == 2
    # Second request continues where page 1 left off.
    assert get_route.calls[1].request.url.params["offset"] == "200"
    assert post_route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_list_machines_paginates_past_page_1() -> None:
    """list_machines wiring: results beyond MAAS's default page are visible."""
    page1 = [
        {"system_id": f"f{i:03}", "hostname": f"other-{i}", "status_name": "Ready"}
        for i in range(200)
    ]
    page2 = [{"system_id": "tail", "hostname": "last-node", "status_name": "Ready"}]
    respx.get("https://maas.example.com/MAAS/api/2.0/machines/").mock(
        side_effect=[
            httpx.Response(200, json=page1),
            httpx.Response(200, json=page2),
        ]
    )
    async with MaasClient(_cfg()) as client:
        result = await ListMachinesTool().run(client)
    assert len(result) == 201
    assert result[-1]["system_id"] == "tail"


@pytest.mark.asyncio
@respx.mock
async def test_find_available_machines_returns_only_ready() -> None:
    """Filters on `status_name` client-side; ignores the integer `status` enum.

    MAAS returns each machine with TWO status fields: `status` (an int,
    like 0 for New) and `status_name` (the string, "New"/"Ready"/...).
    Filtering on `status` is a bug — we filter on `status_name`.
    """
    route = respx.get("https://maas.example.com/MAAS/api/2.0/machines/").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"system_id": "a", "hostname": "n1", "status": 5, "status_name": "Ready"},
                {"system_id": "b", "hostname": "n2", "status": 2, "status_name": "Deployed"},
                {"system_id": "c", "hostname": "n3", "status": 5, "status_name": "Ready"},
            ],
        )
    )
    async with MaasClient(_cfg()) as client:
        tool = FindAvailableMachinesTool()
        result = await tool.run(client)
    assert {m["system_id"] for m in result} == {"a", "c"}
    # The fix must NOT pass ?status=... — MAAS rejects it with 400.
    # `?limit=&offset=` from auto-pagination IS allowed.
    sent_url = str(route.calls.last.request.url)
    assert "status=" not in sent_url, f"MAAS-rejected ?status= in {sent_url}"


@pytest.mark.asyncio
@respx.mock
async def test_find_available_machines_filters_by_hostname() -> None:
    respx.get("https://maas.example.com/MAAS/api/2.0/machines/").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"system_id": "a", "hostname": "node-1", "status_name": "Ready"},
                {"system_id": "b", "hostname": "node-2", "status_name": "Ready"},
            ],
        )
    )
    async with MaasClient(_cfg()) as client:
        result = await FindAvailableMachinesTool().run(client, hostname="node-2")
    assert [m["system_id"] for m in result] == ["b"]


@pytest.mark.asyncio
@respx.mock
async def test_find_available_machines_filters_by_pool() -> None:
    respx.get("https://maas.example.com/MAAS/api/2.0/machines/").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "system_id": "a",
                    "hostname": "n1",
                    "status_name": "Ready",
                    "pool": {"name": "default"},
                },
                {
                    "system_id": "b",
                    "hostname": "n2",
                    "status_name": "Ready",
                    "pool": {"name": "gpu"},
                },
            ],
        )
    )
    async with MaasClient(_cfg()) as client:
        result = await FindAvailableMachinesTool().run(client, pool="gpu")
    assert [m["system_id"] for m in result] == ["b"]


@pytest.mark.asyncio
@respx.mock
async def test_find_available_machines_returns_slim_view() -> None:
    """Output shape matches list_machines — only 6 keys, no raw MAAS bloat."""
    respx.get("https://maas.example.com/MAAS/api/2.0/machines/").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "system_id": "a",
                    "hostname": "n1",
                    "status_name": "Ready",
                    "power_state": "off",
                    "tag_names": ["gpu"],
                    "pool": {"name": "default"},
                    # Fields that must NOT appear in the slim view:
                    "blockdevice_set": [{"id": 1}],
                    "cpu_count": 48,
                    "memory": 1234,
                }
            ],
        )
    )
    async with MaasClient(_cfg()) as client:
        result = await FindAvailableMachinesTool().run(client)
    assert result == [
        {
            "system_id": "a",
            "hostname": "n1",
            "status_name": "Ready",
            "power_state": "off",
            "tag_names": ["gpu"],
            "pool": "default",
        }
    ]


@pytest.mark.asyncio
@respx.mock
async def test_find_available_machines_returns_empty_when_none() -> None:
    """No matches → empty list, never raise."""
    respx.get("https://maas.example.com/MAAS/api/2.0/machines/").mock(
        return_value=httpx.Response(
            200,
            json=[{"system_id": "a", "hostname": "n1", "status_name": "New"}],
        )
    )
    async with MaasClient(_cfg()) as client:
        result = await FindAvailableMachinesTool().run(client)  # default Ready
    assert result == []


@pytest.mark.asyncio
@respx.mock
async def test_release_machine_calls_release_endpoint() -> None:
    route = respx.post("https://maas.example.com/MAAS/api/2.0/machines/abc/op-release").mock(
        return_value=httpx.Response(200, json={})
    )
    async with MaasClient(_cfg()) as client:
        await ReleaseMachineTool().run(client, system_id="abc", comment="done", confirm=True)
    sent = route.calls.last.request
    assert route.call_count == 1
    assert "comment" in sent.read().decode()


@pytest.mark.asyncio
@respx.mock
async def test_release_machine_erase_defaults_to_true() -> None:
    route = respx.post("https://maas.example.com/MAAS/api/2.0/machines/abc/op-release").mock(
        return_value=httpx.Response(200, json={})
    )
    async with MaasClient(_cfg()) as client:
        await ReleaseMachineTool().run(client, system_id="abc", confirm=True)
    body = route.calls.last.request.read().decode()
    # erase=true must be sent even without explicit opt-in
    assert 'name="erase"' in body
    assert "\r\ntrue\r\n" in body


@pytest.mark.asyncio
@respx.mock
async def test_release_machine_requires_confirm() -> None:
    route = respx.post("https://maas.example.com/MAAS/api/2.0/machines/abc/op-release").mock(
        return_value=httpx.Response(200, json={})
    )
    async with MaasClient(_cfg()) as client:
        with pytest.raises(ValueError, match="confirm=True"):
            await ReleaseMachineTool().run(client, system_id="abc")
    # Gate runs before any MAAS call — the mocked endpoint must NOT be hit.
    assert route.call_count == 0


@pytest.mark.asyncio
@respx.mock
async def test_power_status_returns_state() -> None:
    respx.get("https://maas.example.com/MAAS/api/2.0/machines/abc/").mock(
        return_value=httpx.Response(200, json={"power_state": "on"})
    )
    async with MaasClient(_cfg()) as client:
        result = await PowerStatusTool().run(client, system_id="abc")
    assert result == "on"


@pytest.mark.asyncio
@respx.mock
async def test_power_control_validates_action() -> None:
    async with MaasClient(_cfg()) as client:
        with pytest.raises(ValueError):
            await PowerControlTool().run(client, system_id="abc", action="explode", confirm=True)


@pytest.mark.asyncio
@respx.mock
async def test_power_control_requires_confirm() -> None:
    """The tool that powers off hardware must refuse confirm=False before any HTTP call."""
    async with MaasClient(_cfg()) as client:
        with pytest.raises(ValueError, match="confirm=True"):
            await PowerControlTool().run(client, system_id="abc", action="off", confirm=False)
    assert not respx.calls


@pytest.mark.asyncio
@respx.mock
async def test_power_control_on_calls_power_on_endpoint() -> None:
    route = respx.post("https://maas.example.com/MAAS/api/2.0/machines/abc/op-power_on").mock(
        return_value=httpx.Response(200, json={})
    )
    async with MaasClient(_cfg()) as client:
        await PowerControlTool().run(client, system_id="abc", action="on", confirm=True)
    assert route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_power_control_off_calls_power_off_endpoint() -> None:
    respx.get("https://maas.example.com/MAAS/api/2.0/machines/abc/").mock(
        return_value=httpx.Response(200, json={"status_name": "Ready"})
    )
    route = respx.post("https://maas.example.com/MAAS/api/2.0/machines/abc/op-power_off").mock(
        return_value=httpx.Response(200, json={})
    )
    async with MaasClient(_cfg()) as client:
        await PowerControlTool().run(client, system_id="abc", action="off", confirm=True)
    assert route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_power_control_refuses_off_when_deploying() -> None:
    """Power-off is refused when machine is DEPLOYING — could corrupt in-flight OS."""
    respx.get("https://maas.example.com/MAAS/api/2.0/machines/abc/").mock(
        return_value=httpx.Response(200, json={"status_name": "Deploying"})
    )
    off_route = respx.post("https://maas.example.com/MAAS/api/2.0/machines/abc/op-power_off").mock(
        return_value=httpx.Response(200, json={})
    )
    async with MaasClient(_cfg()) as client:
        with pytest.raises(ValueError):
            await PowerControlTool().run(client, system_id="abc", action="off", confirm=True)
    assert off_route.call_count == 0


@pytest.mark.asyncio
@respx.mock
async def test_power_control_cycle_calls_off_then_on() -> None:
    respx.get("https://maas.example.com/MAAS/api/2.0/machines/abc/").mock(
        return_value=httpx.Response(200, json={"status_name": "Ready"})
    )
    off_route = respx.post("https://maas.example.com/MAAS/api/2.0/machines/abc/op-power_off").mock(
        return_value=httpx.Response(200, json={})
    )
    on_route = respx.post("https://maas.example.com/MAAS/api/2.0/machines/abc/op-power_on").mock(
        return_value=httpx.Response(200, json={})
    )
    async with MaasClient(_cfg()) as client:
        await PowerControlTool().run(client, system_id="abc", action="cycle", confirm=True)
    assert off_route.call_count == 1
    assert on_route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_power_control_on_by_hostname_resolves_then_posts() -> None:
    """Hostname path: resolve GET, then the on POST is byte-identical to system_id path."""
    resolve_route = respx.get(
        "https://maas.example.com/MAAS/api/2.0/machines/",
        params={"hostname": "node-1"},
    ).mock(return_value=httpx.Response(200, json=[{"system_id": "xy7zab"}]))
    on_route = respx.post(
        "https://maas.example.com/MAAS/api/2.0/machines/xy7zab/op-power_on"
    ).mock(return_value=httpx.Response(200, json={}))
    async with MaasClient(_cfg()) as client:
        await PowerControlTool().run(client, hostname="node-1", action="on", confirm=True)
    assert resolve_route.call_count == 1
    assert on_route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_release_machine_by_hostname_resolves_then_posts() -> None:
    """Hostname path: resolve GET, then the release POST targets the resolved system_id."""
    resolve_route = respx.get(
        "https://maas.example.com/MAAS/api/2.0/machines/",
        params={"hostname": "node-1"},
    ).mock(return_value=httpx.Response(200, json=[{"system_id": "xy7zab"}]))
    release_route = respx.post(
        "https://maas.example.com/MAAS/api/2.0/machines/xy7zab/op-release"
    ).mock(return_value=httpx.Response(200, json={}))
    async with MaasClient(_cfg()) as client:
        await ReleaseMachineTool().run(client, hostname="node-1", confirm=True)
    assert resolve_route.call_count == 1
    assert release_route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_wait_for_state_polls_until_match() -> None:
    routes = respx.get("https://maas.example.com/MAAS/api/2.0/machines/abc/")
    routes.mock(
        side_effect=[
            httpx.Response(200, json={"status_name": "Deploying"}),
            httpx.Response(200, json={"status_name": "Deploying"}),
            httpx.Response(200, json={"status_name": "Deployed"}),
        ]
    )
    async with MaasClient(_cfg()) as client:
        result = await WaitForStateTool().run(
            client, system_id="abc", target_states=["Deployed", "Failed"], timeout_seconds=10
        )
    assert result["status_name"] == "Deployed"


@pytest.mark.asyncio
@respx.mock
async def test_list_machines_returns_slim_view() -> None:
    respx.get("https://maas.example.com/MAAS/api/2.0/machines/").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "system_id": "a",
                    "hostname": "n1",
                    "status_name": "Ready",
                    "power_state": "off",
                    "tag_names": ["fast"],
                    "pool": {"name": "default"},
                },
            ],
        )
    )
    async with MaasClient(_cfg()) as client:
        result = await ListMachinesTool().run(client, status="Ready")
    assert result == [
        {
            "system_id": "a",
            "hostname": "n1",
            "status_name": "Ready",
            "power_state": "off",
            "tag_names": ["fast"],
            "pool": "default",
        }
    ]


@pytest.mark.asyncio
@respx.mock
async def test_get_machine_by_hostname() -> None:
    respx.get("https://maas.example.com/MAAS/api/2.0/machines/").mock(
        return_value=httpx.Response(
            200,
            json=[{"system_id": "a", "hostname": "node-1"}],
        )
    )
    async with MaasClient(_cfg()) as client:
        result = await GetMachineTool().run(client, identifier="node-1")
    assert result["system_id"] == "a"


@pytest.mark.asyncio
@respx.mock
async def test_tag_machine_uses_add_endpoint() -> None:
    respx.get("https://maas.example.com/MAAS/api/2.0/machines/").mock(
        return_value=httpx.Response(
            200,
            json=[{"system_id": "a", "hostname": "node-1"}],
        )
    )
    route = respx.post("https://maas.example.com/MAAS/api/2.0/tags/fast/op-update_nodes").mock(
        return_value=httpx.Response(200, json={})
    )
    async with MaasClient(_cfg()) as client:
        await TagMachineTool().run(client, hostname="node-1", tag="fast", confirm=True)
    assert route.call_count == 1
    body = route.calls.last.request.read().decode()
    # The system_id is sent as a multipart `add` field on the tag endpoint,
    # not as a query string or path suffix.
    assert 'name="add"' in body
    assert "\r\na\r\n" in body
    # And the URL has no query string — it's all in the body.
    assert not route.calls.last.request.url.params


@pytest.mark.asyncio
@respx.mock
async def test_untag_machine_uses_remove_endpoint() -> None:
    respx.get("https://maas.example.com/MAAS/api/2.0/machines/").mock(
        return_value=httpx.Response(
            200,
            json=[{"system_id": "a", "hostname": "node-1"}],
        )
    )
    route = respx.post("https://maas.example.com/MAAS/api/2.0/tags/fast/op-update_nodes").mock(
        return_value=httpx.Response(200, json={})
    )
    async with MaasClient(_cfg()) as client:
        await UntagMachineTool().run(client, hostname="node-1", tag="fast", confirm=True)
    assert route.call_count == 1
    body = route.calls.last.request.read().decode()
    assert 'name="remove"' in body
    assert "\r\na\r\n" in body


@pytest.mark.asyncio
@respx.mock
async def test_deploy_machine_requires_confirm() -> None:
    """The tool that wipes+reinstalls a machine must refuse confirm=False before any HTTP call."""
    async with MaasClient(_cfg()) as client:
        with pytest.raises(ValueError, match="confirm=True"):
            await DeployMachineTool().run(
                client, system_id="abc", distro="ubuntu/jammy", confirm=False
            )
    assert not respx.calls


@pytest.mark.asyncio
@respx.mock
async def test_deploy_machine_sets_distro_and_waits() -> None:
    respx.post("https://maas.example.com/MAAS/api/2.0/machines/abc/op-deploy").mock(
        return_value=httpx.Response(200, json={})
    )
    respx.get("https://maas.example.com/MAAS/api/2.0/machines/abc/").mock(
        side_effect=[
            httpx.Response(
                200, json={"status_name": "Deploying", "commissioning_status_name": "Passed"}
            ),
            httpx.Response(200, json={"status_name": "Deploying"}),
            httpx.Response(200, json={"status_name": "Deployed"}),
        ]
    )
    async with MaasClient(_cfg()) as client:
        result = await DeployMachineTool().run(
            client,
            system_id="abc",
            distro="ubuntu/jammy",
            timeout_seconds=60,
            confirm=True,
        )
    assert result["status_name"] == "Deployed"


@pytest.mark.asyncio
@respx.mock
async def test_deploy_machine_commissions_when_new() -> None:
    commission_route = respx.post(
        "https://maas.example.com/MAAS/api/2.0/machines/abc/op-commission"
    ).mock(return_value=httpx.Response(200, json={}))
    respx.post("https://maas.example.com/MAAS/api/2.0/machines/abc/op-deploy").mock(
        return_value=httpx.Response(200, json={})
    )
    respx.get("https://maas.example.com/MAAS/api/2.0/machines/abc/").mock(
        side_effect=[
            # Pre-flight fetch: machine is NEW and not commissioned.
            httpx.Response(
                200,
                json={"status_name": "New", "commissioning_status_name": "Pending"},
            ),
            # Poll after commission returns READY.
            httpx.Response(200, json={"status_name": "Ready"}),
            # Final poll after deploy.
            httpx.Response(200, json={"status_name": "Deployed"}),
        ]
    )
    async with MaasClient(_cfg()) as client:
        result = await DeployMachineTool().run(
            client,
            system_id="abc",
            distro="ubuntu/jammy",
            timeout_seconds=60,
            confirm=True,
        )
    assert result["status_name"] == "Deployed"
    assert commission_route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_deploy_machine_skips_commission_when_already_commissioned() -> None:
    """READY + PASSED commissioning_status → no /op-commission POST."""
    commission_route = respx.post(
        "https://maas.example.com/MAAS/api/2.0/machines/abc/op-commission"
    ).mock(return_value=httpx.Response(200, json={}))
    deploy_route = respx.post("https://maas.example.com/MAAS/api/2.0/machines/abc/op-deploy").mock(
        return_value=httpx.Response(200, json={})
    )
    respx.get("https://maas.example.com/MAAS/api/2.0/machines/abc/").mock(
        side_effect=[
            httpx.Response(
                200, json={"status_name": "Ready", "commissioning_status_name": "Passed"}
            ),
            httpx.Response(200, json={"status_name": "Deployed"}),
        ]
    )
    async with MaasClient(_cfg()) as client:
        result = await DeployMachineTool().run(
            client,
            system_id="abc",
            distro="ubuntu/jammy",
            timeout_seconds=60,
            confirm=True,
        )
    assert result["status_name"] == "Deployed"
    assert commission_route.call_count == 0
    assert deploy_route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_deploy_machine_refuses_when_commission_failed() -> None:
    """If commissioning ends in FAILED, raise — don't try to deploy."""
    from maasmcp.maas.errors import MCPUpstreamError

    respx.post("https://maas.example.com/MAAS/api/2.0/machines/abc/op-commission").mock(
        return_value=httpx.Response(200, json={})
    )
    deploy_route = respx.post("https://maas.example.com/MAAS/api/2.0/machines/abc/op-deploy").mock(
        return_value=httpx.Response(200, json={})
    )
    respx.get("https://maas.example.com/MAAS/api/2.0/machines/abc/").mock(
        side_effect=[
            httpx.Response(
                200, json={"status_name": "New", "commissioning_status_name": "Pending"}
            ),
            # MAAS Title-cases failure states; there is no bare "Failed".
            httpx.Response(200, json={"status_name": "Failed commissioning"}),
        ]
    )
    async with MaasClient(_cfg()) as client:
        with pytest.raises(MCPUpstreamError):
            await DeployMachineTool().run(
                client,
                system_id="abc",
                distro="ubuntu/jammy",
                timeout_seconds=60,
                confirm=True,
            )
    assert deploy_route.call_count == 0


@pytest.mark.asyncio
@respx.mock
async def test_deploy_machine_raises_when_deployment_fails() -> None:
    """A 'Failed deployment' outcome raises promptly instead of returning it."""
    from maasmcp.maas.errors import MCPUpstreamError

    respx.post("https://maas.example.com/MAAS/api/2.0/machines/abc/op-deploy").mock(
        return_value=httpx.Response(200, json={})
    )
    respx.get("https://maas.example.com/MAAS/api/2.0/machines/abc/").mock(
        side_effect=[
            httpx.Response(
                200, json={"status_name": "Ready", "commissioning_status_name": "Passed"}
            ),
            httpx.Response(200, json={"status_name": "Failed deployment"}),
        ]
    )
    async with MaasClient(_cfg()) as client:
        with pytest.raises(MCPUpstreamError):
            await DeployMachineTool().run(
                client,
                system_id="abc",
                distro="ubuntu/jammy",
                timeout_seconds=60,
                confirm=True,
            )


@pytest.mark.asyncio
@respx.mock
async def test_summary_counts_machines_by_status_and_pool() -> None:
    respx.get("https://maas.example.com/MAAS/api/2.0/machines/").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"status_name": "Ready", "pool": {"name": "p1"}, "memory": 1024, "cpu_count": 4},
                {"status_name": "Ready", "pool": {"name": "p2"}, "memory": 2048, "cpu_count": 8},
                {"status_name": "Deployed", "pool": {"name": "p1"}, "memory": 1024, "cpu_count": 4},
            ],
        )
    )
    respx.get("https://maas.example.com/MAAS/api/2.0/pods/").mock(
        return_value=httpx.Response(200, json=[])
    )
    async with MaasClient(_cfg()) as client:
        result = await SummaryTool().run(client)
    assert result["by_status"] == {"Ready": 2, "Deployed": 1}
    assert result["by_pool"] == {"p1": 2, "p2": 1}
    assert result["total_memory_mb"] == 4096
    assert result["total_cpu_count"] == 16


@pytest.mark.asyncio
@respx.mock
async def test_summary_includes_by_zone_and_pod_counts() -> None:
    respx.get("https://maas.example.com/MAAS/api/2.0/machines/").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "status_name": "Ready",
                    "pool": {"name": "p1"},
                    "zone": {"name": "z1"},
                    "memory": 1024,
                    "cpu_count": 4,
                },
                {
                    "status_name": "Ready",
                    "pool": {"name": "p2"},
                    "zone": {"name": "z1"},
                    "memory": 2048,
                    "cpu_count": 8,
                },
                {
                    "status_name": "Deployed",
                    "pool": {"name": "p1"},
                    "zone": {"name": "z2"},
                    "memory": 1024,
                    "cpu_count": 4,
                },
            ],
        )
    )
    respx.get("https://maas.example.com/MAAS/api/2.0/pods/").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"id": 1, "status_name": "Ready"},
                {"id": 2, "status_name": "Ready"},
                {"id": 3, "status_name": "Broken"},
            ],
        )
    )
    async with MaasClient(_cfg()) as client:
        result = await SummaryTool().run(client)
    assert result["by_zone"] == {"z1": 2, "z2": 1}
    assert result["pod_count"] == 3
    assert result["pod_count_by_status"] == {"Ready": 2, "Broken": 1}


@pytest.mark.asyncio
@respx.mock
async def test_list_machines_filters_by_pool_tag_glob() -> None:
    respx.get("https://maas.example.com/MAAS/api/2.0/machines/").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "system_id": "a",
                    "hostname": "node-a",
                    "status_name": "Ready",
                    "power_state": "off",
                    "tag_names": ["fast"],
                    "pool": {"name": "default"},
                },
                {
                    "system_id": "b",
                    "hostname": "node-b",
                    "status_name": "Ready",
                    "power_state": "off",
                    "tag_names": ["slow"],
                    "pool": {"name": "other"},
                },
                {
                    "system_id": "c",
                    "hostname": "node-c",
                    "status_name": "Ready",
                    "power_state": "off",
                    "tag_names": ["fast"],
                    "pool": {"name": "other"},
                },
            ],
        )
    )
    async with MaasClient(_cfg()) as client:
        result = await ListMachinesTool().run(
            client, pool="other", tag="fast", hostname_glob="node-c"
        )
    assert [m["system_id"] for m in result] == ["c"]


@pytest.mark.asyncio
@respx.mock
async def test_get_machine_by_hex_system_id() -> None:
    respx.get("https://maas.example.com/MAAS/api/2.0/machines/abcdef/").mock(
        return_value=httpx.Response(
            200,
            json={
                "system_id": "abcdef",
                "hostname": "node-1",
                "tag_names": ["fast"],
                "pool": {"name": "default"},
                "owner": {"username": "admin"},
                "power_state": "on",
                "osystem": "ubuntu",
                "distro_series": "jammy",
                "last_commissioned": "2024-01-01T00:00:00Z",
            },
        )
    )
    async with MaasClient(_cfg()) as client:
        result = await GetMachineTool().run(client, identifier="abcdef")
    assert result["system_id"] == "abcdef"
    assert result["pool"] == "default"
    assert result["owner"] == "admin"
    assert result["os"] == "ubuntu jammy"


@pytest.mark.asyncio
@respx.mock
async def test_tag_machine_raises_when_hostname_not_found() -> None:
    respx.get("https://maas.example.com/MAAS/api/2.0/machines/").mock(
        return_value=httpx.Response(200, json=[])
    )
    async with MaasClient(_cfg()) as client:
        with pytest.raises(ValueError):
            await TagMachineTool().run(client, hostname="missing", tag="fast", confirm=True)


@pytest.mark.asyncio
@respx.mock
async def test_tag_machine_requires_confirm() -> None:
    """confirm=False fires the gate before any mutating POST. The hostname
    resolution GET now runs BEFORE the gate (tree-wide rule, see
    test_machines_set_zone_requires_confirm)."""
    resolve_route = respx.get("https://maas.example.com/MAAS/api/2.0/machines/").mock(
        return_value=httpx.Response(200, json=[{"system_id": "a", "hostname": "node-1"}])
    )
    post_route = respx.post(
        "https://maas.example.com/MAAS/api/2.0/tags/fast/op-update_nodes"
    ).mock(return_value=httpx.Response(200, json={}))
    async with MaasClient(_cfg()) as client:
        with pytest.raises(ValueError, match="confirm=True"):
            await TagMachineTool().run(client, hostname="node-1", tag="fast", confirm=False)
    assert resolve_route.called
    assert not post_route.called


@pytest.mark.asyncio
@respx.mock
async def test_untag_machine_raises_when_hostname_not_found() -> None:
    respx.get("https://maas.example.com/MAAS/api/2.0/machines/").mock(
        return_value=httpx.Response(200, json=[])
    )
    async with MaasClient(_cfg()) as client:
        with pytest.raises(ValueError):
            await UntagMachineTool().run(client, hostname="missing", tag="fast", confirm=True)


@pytest.mark.asyncio
@respx.mock
async def test_untag_machine_requires_confirm() -> None:
    """confirm=False fires the gate before any mutating POST. The hostname
    resolution GET now runs BEFORE the gate (tree-wide rule, see
    test_machines_set_zone_requires_confirm)."""
    resolve_route = respx.get("https://maas.example.com/MAAS/api/2.0/machines/").mock(
        return_value=httpx.Response(200, json=[{"system_id": "a", "hostname": "node-1"}])
    )
    post_route = respx.post(
        "https://maas.example.com/MAAS/api/2.0/tags/fast/op-update_nodes"
    ).mock(return_value=httpx.Response(200, json={}))
    async with MaasClient(_cfg()) as client:
        with pytest.raises(ValueError, match="confirm=True"):
            await UntagMachineTool().run(client, hostname="node-1", tag="fast", confirm=False)
    assert resolve_route.called
    assert not post_route.called


@pytest.mark.asyncio
@respx.mock
async def test_get_machine_raises_when_hostname_missing() -> None:
    respx.get("https://maas.example.com/MAAS/api/2.0/machines/").mock(
        return_value=httpx.Response(200, json=[])
    )
    # Hostname miss falls through to a system_id GET (non-hex ids are legal),
    # which 404s too — both misses together produce the ValueError.
    respx.get("https://maas.example.com/MAAS/api/2.0/machines/ghost/").mock(
        return_value=httpx.Response(404)
    )
    async with MaasClient(_cfg()) as client:
        with pytest.raises(ValueError, match="hostname or system_id"):
            await GetMachineTool().run(client, identifier="ghost")


@pytest.mark.asyncio
@respx.mock
async def test_wait_for_state_times_out_with_timeout_error() -> None:
    """Local poll deadline raises builtin TimeoutError, not MCPUpstreamTimeout
    (which would falsely signal a MAAS outage)."""
    respx.get("https://maas.example.com/MAAS/api/2.0/machines/abc/").mock(
        return_value=httpx.Response(200, json={"status_name": "Deploying"})
    )
    async with MaasClient(_cfg()) as client:
        with pytest.raises(TimeoutError, match="did not reach"):
            await WaitForStateTool().run(
                client, system_id="abc", target_states=["Ready"], timeout_seconds=0
            )


@pytest.mark.asyncio
@respx.mock
async def test_tag_machine_quotes_traversal_in_tag_name() -> None:
    """A crafted tag containing ../ must not reshape the request path —
    quote_segment makes it inert (encoded, un-decodable to traversal)."""
    respx.get("https://maas.example.com/MAAS/api/2.0/machines/").mock(
        return_value=httpx.Response(200, json=[{"system_id": "a", "hostname": "node-1"}])
    )
    route = respx.post(
        "https://maas.example.com/MAAS/api/2.0/tags/x%2F..%2Fmachines%2Fabc/op-update_nodes"
    ).mock(return_value=httpx.Response(200, json={}))
    async with MaasClient(_cfg()) as client:
        await TagMachineTool().run(client, hostname="node-1", tag="x/../machines/abc", confirm=True)
    # Matching the %-encoded route proves quoting happened: unquoted, httpx
    # would normalize ../ out of the path and this route would never match.
    assert route.call_count == 1
    raw_path = route.calls.last.request.url.raw_path
    assert raw_path.endswith(b"/api/2.0/tags/x%2F..%2Fmachines%2Fabc/op-update_nodes"), raw_path
