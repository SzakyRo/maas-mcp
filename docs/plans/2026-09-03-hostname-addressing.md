# Dual system_id/hostname Addressing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every one of the 62 machine-addressed MCP tools accepts `system_id` or `hostname` (exactly one), resolved server-side.

**Architecture:** One shared resolver module (`_resolve.py`) does hostname→system_id lookups via MAAS's exact-match `/machines/?hostname=` filter; every curated tool gains an optional `hostname` param and calls the resolver first. Bulk/list ops use a single fleet fetch + in-memory map.

**Tech Stack:** Python 3.11+, FastMCP (mcp SDK), pydantic, pytest + pytest-asyncio (auto mode) + respx for HTTP mocking.

**Spec:** `docs/specs/2026-09-03-hostname-addressing-design.md`

## Global Constraints

- **Non-breaking:** no param renames, no removals; `system_id`/`system_ids` change from required to optional only.
- Provide **exactly one** of `system_id`/`hostname`; both set + conflicting → `ValueError`; neither → `ValueError`.
- No existence pre-check when only `system_id` is passed — return it unverified.
- Hostname lookup is `GET /api/2.0/machines/?hostname=<exact>` — MAAS exact-matches this filter.
- Bulk resolution = **one** fleet list call + in-memory map, never N lookups. Handle both response shapes: bare list (user's MAAS quirk) and `{"results": [...]}` dict.
- Because `system_id` gains a default (`= None`), every parameter after it must become keyword-only — insert `*` into each touched `run()` signature. Existing tests mostly call by keyword; fix any positional call sites that break.
- Run tests with `uv run pytest <path> -v` from the repo root; asyncio_mode is already `auto`.
- Commit after every task.

---

### Task 1: Shared resolver module `_resolve.py`

**Files:**
- Create: `src/maasmcp/curated/_resolve.py`
- Test: `tests/unit/curated/test_resolve.py`

**Interfaces:**
- Produces:
  - `async def resolve_system_id(client: MaasClient, system_id: str | None, hostname: str | None) -> str` — used by Tasks 2, 3, 4, 5, 7.
  - `async def resolve_hostnames(client: MaasClient, hostnames: list[str]) -> tuple[dict[str, str], list[str]]` — returns `(hostname→system_id map, unmatched hostnames)`; used by Task 6.
  - `async def _machine_list(client: MaasClient) -> list[dict]` — internal; normalizes bare-list and `{"results": [...]}` responses.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/curated/test_resolve.py`:

```python
import pytest
import respx
from httpx import Response

from maasmcp.config import MaasmcpConfig
from maasmcp.curated._resolve import resolve_hostnames, resolve_system_id
from maasmcp.maas.client import MaasClient

pytestmark = pytest.mark.asyncio


def _client(monkeypatch) -> MaasClient:
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    cfg = MaasmcpConfig.load(None)
    c = MaasClient(cfg.maas)
    c.base_url = cfg.maas.base_url
    return c


async def test_neither_raises(monkeypatch):
    c = _client(monkeypatch)
    async with c:
        with pytest.raises(ValueError, match="exactly one"):
            await resolve_system_id(c, None, None)


async def test_system_id_only_no_http(monkeypatch):
    """system_id-only resolution MUST NOT touch the network."""
    c = _client(monkeypatch)
    with respx.mock(base_url=c.base_url, assert_all_called=False) as mock:
        route = mock.get("/api/2.0/machines/").mock(return_value=Response(200, json=[]))
        async with c:
            assert await resolve_system_id(c, "abc123", None) == "abc123"
    assert not route.called


async def test_hostname_hit(monkeypatch):
    c = _client(monkeypatch)
    with respx.mock(base_url=c.base_url, assert_all_called=False) as mock:
        route = mock.get("/api/2.0/machines/", params={"hostname": "node-1"}).mock(
            return_value=Response(200, json=[{"system_id": "xy7zab", "hostname": "node-1"}])
        )
        async with c:
            assert await resolve_system_id(c, None, "node-1") == "xy7zab"
    assert route.called


async def test_hostname_miss(monkeypatch):
    c = _client(monkeypatch)
    with respx.mock(base_url=c.base_url, assert_all_called=False) as mock:
        mock.get("/api/2.0/machines/").mock(return_value=Response(200, json=[]))
        async with c:
            with pytest.raises(ValueError, match="no machine found with hostname"):
                await resolve_system_id(c, None, "ghost")


async def test_both_matching(monkeypatch):
    c = _client(monkeypatch)
    with respx.mock(base_url=c.base_url, assert_all_called=False) as mock:
        mock.get("/api/2.0/machines/", params={"hostname": "node-1"}).mock(
            return_value=Response(200, json=[{"system_id": "xy7zab"}])
        )
        async with c:
            assert await resolve_system_id(c, "xy7zab", "node-1") == "xy7zab"


async def test_both_conflicting(monkeypatch):
    c = _client(monkeypatch)
    with respx.mock(base_url=c.base_url, assert_all_called=False) as mock:
        mock.get("/api/2.0/machines/", params={"hostname": "node-1"}).mock(
            return_value=Response(200, json=[{"system_id": "xy7zab"}])
        )
        async with c:
            with pytest.raises(ValueError, match="does not belong to hostname"):
                await resolve_system_id(c, "other9", "node-1")


async def test_machine_list_handles_results_dict(monkeypatch):
    """Upstream-style paginated envelope must work too."""
    c = _client(monkeypatch)
    with respx.mock(base_url=c.base_url, assert_all_called=False) as mock:
        mock.get("/api/2.0/machines/").mock(
            return_value=Response(200, json={"count": 1, "results": [{"system_id": "s1", "hostname": "h1"}]})
        )
        async with c:
            mapping, missing = await resolve_hostnames(c, ["h1", "h2"])
    assert mapping == {"h1": "s1"}
    assert missing == ["h2"]


async def test_resolve_hostnames_empty(monkeypatch):
    c = _client(monkeypatch)
    async with c:
        assert await resolve_hostnames(c, []) == ({}, [])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/curated/test_resolve.py -v`
Expected: FAIL — `ModuleNotFoundError: maasmcp.curated._resolve`

- [ ] **Step 3: Implement `src/maasmcp/curated/_resolve.py`**

```python
"""Shared hostname↔system_id resolution for curated verbs.

MAAS addresses machines by system_id in URL paths; hostname exists upstream
only as an exact-match list filter (GET /machines/?hostname=...). Every
machine-addressed tool accepts exactly one of system_id/hostname and resolves
through here so the lookup logic and error messages stay identical across the
~60 verbs that use it.
"""

from __future__ import annotations

from typing import Any

from maasmcp.maas.client import MaasClient


async def _machine_list(client: MaasClient, params: dict[str, Any] | None = None) -> list[dict]:
    """Fetch the machine collection, normalizing both known response shapes.

    MAAS normally returns a bare list; some deployments wrap it as
    ``{"count": N, "results": [...]}``. Handle both.
    """
    machines: Any = await client.get("/api/2.0/machines/", params=params)
    if isinstance(machines, dict):
        machines = machines.get("results", [])
    if not isinstance(machines, list):
        raise ValueError("unexpected response listing machines")
    return machines


async def _lookup_hostname(client: MaasClient, hostname: str) -> str:
    hits = await _machine_list(client, {"hostname": hostname})
    if not hits:
        raise ValueError(f"no machine found with hostname {hostname!r}")
    # MAAS enforces unique hostnames; if a misbehaving server returns >1,
    # first-hit matches the historical tag_machine behavior.
    sid = hits[0].get("system_id")
    if not isinstance(sid, str) or not sid:
        raise ValueError(f"machine with hostname {hostname!r} has no system_id")
    return sid


async def resolve_system_id(
    client: MaasClient,
    system_id: str | None,
    hostname: str | None,
) -> str:
    """Resolve exactly one of system_id/hostname to a system_id.

    system_id-only is returned unverified (no extra round-trip; MAAS errors
    surface on the real call). hostname triggers one exact-match list call.
    Both set must agree, else ValueError.
    """
    if system_id is None and hostname is None:
        raise ValueError("must provide exactly one of system_id or hostname")
    if hostname is not None:
        resolved = await _lookup_hostname(client, hostname)
        if system_id is not None and resolved != system_id:
            raise ValueError(
                f"system_id {system_id!r} does not belong to hostname {hostname!r} "
                f"(it resolves to {resolved!r})"
            )
        return resolved
    assert system_id is not None
    return system_id


async def resolve_hostnames(
    client: MaasClient, hostnames: list[str]
) -> tuple[dict[str, str], list[str]]:
    """Resolve many hostnames with ONE fleet fetch + in-memory map.

    Returns (hostname→system_id map, list of unmatched hostnames). An empty
    input short-circuits without any HTTP call.
    """
    if not hostnames:
        return {}, []
    machines = await _machine_list(client)
    by_hostname = {
        m["hostname"]: m["system_id"]
        for m in machines
        if isinstance(m, dict)
        and isinstance(m.get("hostname"), str)
        and isinstance(m.get("system_id"), str)
    }
    mapping = {h: by_hostname[h] for h in hostnames if h in by_hostname}
    missing = [h for h in hostnames if h not in by_hostname]
    return mapping, missing
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/curated/test_resolve.py -v`
Expected: 8 PASS

- [ ] **Step 5: Commit**

```bash
git add src/maasmcp/curated/_resolve.py tests/unit/curated/test_resolve.py
git commit -m "feat: shared hostname→system_id resolver for curated verbs"
```

---

### Task 2: Pilot the pattern on `power_status`

**Files:**
- Modify: `src/maasmcp/curated/power_status.py`
- Test: `tests/unit/curated/test_power_status.py` (create if missing; check first)

**Interfaces:**
- Consumes: `resolve_system_id` from Task 1.
- Produces: the mechanical edit pattern reused verbatim in Tasks 3–5.

Check whether `tests/unit/curated/test_power_status.py` already exists and what its helper setup looks like; reuse its client-construction helper if one exists.

- [ ] **Step 1: Write the failing test** (append to the tool's test file)

```python
async def test_power_status_by_hostname(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
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
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    async with maas_client:
        with pytest.raises(ValueError, match="exactly one"):
            await PowerStatusTool().run(maas_client)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/curated/test_power_status.py -v`
Expected: FAIL — `TypeError: ... unexpected keyword argument 'hostname'` (and existing tests may fail with `TypeError` if signature changed prematurely — do Step 1 first, before touching the tool).

- [ ] **Step 3: Apply the mechanical edit to `power_status.py`**

New `run()` signature and prologue (this exact shape is the pattern for all single-id tools):

```python
    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        system_id: Annotated[
            str | None,
            Field(
                description="MAAS system_id of the machine. "
                "Provide this or hostname, exactly one."
            ),
        ] = None,
        *,
        hostname: Annotated[
            str | None,
            Field(description="Exact hostname of the machine; resolved to system_id server-side."),
        ] = None,
    ) -> str:
        system_id = await resolve_system_id(client, system_id, hostname)
        validate_system_id(system_id)
        machine = await client.get(f"/api/2.0/machines/{system_id}/")
```

Add import: `from maasmcp.curated._resolve import resolve_system_id`

Append to the description string, immediately before the gating sentence ("Read-only; no confirmation needed."):
`"Accepts system_id or hostname (provide exactly one). "`

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/curated/test_power_status.py -v`
Expected: all PASS, including the pre-existing tests (proof of backwards compatibility)

- [ ] **Step 5: Commit**

```bash
git add src/maasmcp/curated/power_status.py tests/unit/curated/test_power_status.py
git commit -m "feat: power_status accepts hostname in addition to system_id"
```

---

### Task 3: Storage batch (31 tools)

**Files (modify each):**
`src/maasmcp/curated/` — `apply_storage_layout.py`, `clear_boot_disk.py`, `create_block_device.py`, `create_logical_volume.py`, `create_partition.py`, `create_raid.py`, `create_volume_group.py`, `delete_block_device.py`, `delete_logical_volume.py`, `delete_partition.py`, `delete_raid.py`, `delete_volume_group.py`, `format_block_device.py`, `format_partition.py`, `get_block_device.py`, `get_partition.py`, `get_raid.py`, `get_volume_group.py`, `list_block_devices.py`, `list_partitions.py`, `list_raids.py`, `list_volume_groups.py`, `mount_block_device.py`, `mount_partition.py`, `set_boot_disk.py`, `storage_summary.py`, `unmount_block_device.py`, `unmount_partition.py`, `update_block_device.py`, `update_raid.py`, `update_volume_group.py`

**Test:** one representative behavior test each for `set_boot_disk`, `create_raid`, `list_block_devices` (append to their existing test files).

**Interfaces:**
- Consumes: `resolve_system_id` from Task 1; the edit pattern from Task 2.
- Produces: nothing new for later tasks.

- [ ] **Step 1: Write the failing representative tests**

For each of `set_boot_disk`, `create_raid`, `list_block_devices`, append a hostname-path test in that tool's existing test file proving: resolve happens (`GET /machines/?hostname=...`) then the byte-identical upstream call the system_id path makes (e.g. `POST /api/2.0/nodes/xy7zab/blockdevices/3/op-set_boot_disk`). Follow the Task 2 test shape: mock `GET /api/2.0/machines/` with `params={"hostname": "node-1"}` returning `Response(200, json=[{"system_id": "xy7zab"}])`, mock the tool's own endpoint, call `run(..., hostname="node-1", confirm=True)`, assert on the upstream route's request.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/curated/test_set_boot_disk.py tests/unit/curated/test_create_raid.py tests/unit/curated/test_list_block_devices.py -v`
Expected: FAIL — unexpected keyword argument 'hostname'

- [ ] **Step 3: Apply the Task 2 mechanical edit to all 31 files**

In each file:

1. Import: `from maasmcp.curated._resolve import resolve_system_id`
2. Signature: change `system_id` to `str | None` with default `None` and description `"MAAS system_id of the machine. Provide this or hostname, exactly one."`; insert `*,` after it (making later params keyword-only); append `hostname: Annotated[str | None, Field(description="Exact hostname of the machine; resolved to system_id server-side.")] = None`.
   - `apply_storage_layout` already has a `confirm` param — `hostname` goes before `confirm` or after; order within the keyword-only block doesn't matter, keep `confirm` last for readability.
3. Prologue: keep existing confirm-gate and validation order; immediately after, insert:
   ```python
   system_id = await resolve_system_id(client, system_id, hostname)
   ```
   All downstream uses of `system_id` (path builders, `_validate_ids(system_id, ...)`) now operate on the resolved id unchanged.
4. Confirm-gate messages that print `system_id`: also print `hostname` (`f"system_id={system_id}, hostname={hostname}"`).
5. Description: append `"Accepts system_id or hostname (provide exactly one). "` before the gating sentence.

If a file in the list turns out to have no `system_id` param in `run()`, skip it and note it in the commit message — the Task 8 guard test is the completeness backstop.

Also run the full existing unit suite for the storage files and fix any test that passed extra positional args (convert to keywords).

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/curated/ -k "boot_disk or raid or block_devices or partition or volume_group or logical_volume or storage_layout or mount or format" -v`
Expected: PASS, old and new

- [ ] **Step 5: Commit**

```bash
git add src/maasmcp/curated/ tests/unit/curated/
git commit -m "feat: storage verbs accept hostname in addition to system_id (31 tools)"
```

---

### Task 4: Network/interface batch (13 tools)

**Files (modify each):**
`src/maasmcp/curated/` — `assign_vlan_to_interface.py`, `create_bond.py`, `create_bridge.py`, `create_interface.py`, `create_interface_vlan.py`, `delete_interface.py`, `get_interface.py`, `link_subnet.py`, `list_interfaces.py`, `network_layout.py`, `unlink_subnet.py`, `update_interface.py` — plus `wait_for_state.py` (lifecycle-ish but simple; keep it here for batch size)

**Test:** one hostname-path behavior test each for `link_subnet` and `network_layout` in their existing test files.

**Interfaces:**
- Consumes: `resolve_system_id` from Task 1; pattern from Task 2.

- [ ] **Step 1: Write the failing representative tests** — same shape as Task 3 Step 1, asserting resolve-then-upstream-call for `link_subnet` (`POST /api/2.0/nodes/xy7zab/interfaces/<id>/?op=link_subnet`) and `network_layout`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/curated/test_link_subnet.py tests/unit/curated/test_network_layout.py -v`
Expected: FAIL — unexpected keyword argument 'hostname'

- [ ] **Step 3: Apply the Task 3 Step 3 mechanical edit to all 13 files** (same 5 sub-steps; identical edit text). Fix any positional call sites in existing tests.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/curated/ -k "interface or bond or bridge or link_subnet or network_layout or vlan_to or wait_for_state" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/maasmcp/curated/ tests/unit/curated/
git commit -m "feat: network verbs accept hostname in addition to system_id (13 tools)"
```

---

### Task 5: Machine lifecycle batch (15 tools)

**Files (modify each):**
`src/maasmcp/curated/` — `deploy_machine.py`, `machine_abort.py`, `machine_commission.py`, `machine_delete.py`, `machine_details.py`, `machine_lock.py`, `machine_mark_broken.py`, `machine_mark_fixed.py`, `machine_power_parameters.py`, `machine_unlock.py`, `machine_update.py`, `machines_power_parameters.py`, `power_control.py`, `release_machine.py`, plus `get_machine.py` is **excluded** (already dual-accept) and `acquire_machine.py` is **excluded** (no system_id param).

**Note:** `machines_power_parameters.py` takes `id` (not `system_id`) — check its signature; if there is no `system_id` param, skip it and note in the commit message.

**Test:** one hostname-path behavior test each for `power_control` and `release_machine` (the two most dangerous) in their existing test files.

**Interfaces:**
- Consumes: `resolve_system_id` from Task 1; pattern from Task 2.

- [ ] **Step 1: Write the failing representative tests** — Task 3 Step 1 shape: `power_control` resolves `hostname="node-1"` then POSTs `/api/2.0/machines/xy7zab/?op=power_on`; `release_machine` resolves then POSTs the release op on the resolved id.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/curated/test_power_control.py tests/unit/curated/test_release_machine.py -v`
Expected: FAIL — unexpected keyword argument 'hostname'

- [ ] **Step 3: Apply the Task 3 Step 3 mechanical edit to all files** (skipping any without a `system_id` param, noting in commit message). Fix positional call sites if any.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/curated/ -k "power_control or release or deploy or machine_" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/maasmcp/curated/ tests/unit/curated/
git commit -m "feat: machine lifecycle verbs accept hostname in addition to system_id (15 tools)"
```

---

### Task 6: Bulk ops + `machines_accept` (5 tools)

**Files:**
- Modify: `src/maasmcp/curated/bulk_tag_machines.py`, `bulk_untag_machines.py`, `bulk_power_control_machines.py`, `bulk_release_machines.py`, `machines_accept.py`
- Test: append hostname tests to `tests/unit/curated/test_bulk_tag_machines.py` (or nearest existing bulk test file) and `tests/unit/curated/test_machines_accept.py`

**Interfaces:**
- Consumes: `resolve_hostnames` from Task 1 (signature: `(client, hostnames) -> (map, missing)`).
- Produces: nothing new for later tasks.

- [ ] **Step 1: Write the failing tests**

For `bulk_tag_machines` (full test, no elisions — note the env boilerplate matches every other curated test file):

```python
async def test_bulk_tag_by_hostnames(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url, assert_all_called=False) as mock:
        mock.get("/api/2.0/machines/").mock(
            return_value=Response(200, json=[
                {"system_id": "aa1", "hostname": "node-1"},
                {"system_id": "bb2", "hostname": "node-2"},
            ])
        )
        tag_route = mock.post("/api/2.0/tags/prod/op-update_nodes").mock(
            return_value=Response(200, json={})
        )
        async with maas_client:
            results = await BulkTagMachinesTool().run(
                maas_client, hostnames=["node-1", "node-2", "ghost"], tag="prod", confirm=True
            )
    assert tag_route.call_count == 2  # only resolved hosts fan out
    assert {r["system_id"] for r in results} == {"aa1", "bb2", "ghost"}
    assert [r for r in results if r["system_id"] == "ghost"][0]["status"] == "error"
```

(Imports per the file's existing header: `pytest`, `respx`, `httpx.Response`, `MaasmcpConfig`, `MaasClient`, the tool class.) Unmatched hostnames produce `{"system_id": <the raw hostname string>, "status": "error", "error": "no machine found with hostname ..."}` entries — the `BulkTagResult` schema already tolerates this since `system_id` values are opaque strings.

For `machines_accept`: `machines` param becomes optional; add `hostnames: list[str] | None`; test that `hostnames=["node-1"]` resolves via one `GET /machines/` and POSTs `machines=<resolved id>`; both-None → `ValueError("exactly one")`-family message.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/curated/test_bulk_tag_machines.py tests/unit/curated/test_machines_accept.py -v`
Expected: FAIL — unexpected keyword argument 'hostnames'

- [ ] **Step 3: Implement the bulk pattern in all 5 files**

In each bulk tool:

```python
        system_ids: Annotated[
            list[str] | None,
            Field(description="List of MAAS system_ids. Provide this or hostnames; union if both.", max_length=500),
        ] = None,
        *,
        hostnames: Annotated[
            list[str] | None,
            Field(description="List of exact hostnames; resolved with one fleet fetch.", max_length=500),
        ] = None,
```

Prologue after the confirm gate:

```python
        if system_ids is None and hostnames is None:
            raise ValueError("must provide system_ids or hostnames (or both)")
        resolved = list(system_ids or [])
        if hostnames:
            mapping, missing = await resolve_hostnames(client, hostnames)
            resolved.extend(mapping.values())
            missing_entries = [
                {"system_id": h, "status": "error",
                 "error": f"no machine found with hostname {h!r}"}
                for h in missing
            ]
        else:
            missing_entries = []
        if not resolved and not missing_entries:
            return []
        results = await <existing fan-out over resolved>
        return [*missing_entries, *results]
```

(`<existing fan-out over resolved>` = the per-host helper loop already in each bulk file — `_tag_one`, `_release_one`, the power-control gather, etc. — unchanged except its input list variable is now `resolved` instead of the old `system_ids` parameter.)

For `machines_accept`, same resolution but single POST body: `{"machines": resolved}`; missing hostnames raise `ValueError` (accept is not per-host tolerant — refusing with a clear message beats silently accepting a subset).

Preserve existing behavior: empty-list-only calls still return `[]` (backwards compat — empty `[]` means "provided, empty", distinct from `None` = "not provided").

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/curated/ -k "bulk or accept" -v`
Expected: PASS, old and new

- [ ] **Step 5: Commit**

```bash
git add src/maasmcp/curated/ tests/unit/curated/
git commit -m "feat: bulk ops and machines_accept accept hostnames lists (one-fetch resolution)"
```

---

### Task 7: `machines_set_zone` + `tag_machine`/`untag_machine` migration

**Files:**
- Modify: `src/maasmcp/curated/machines_set_zone.py`, `tag_machine.py`, `untag_machine.py`
- Test: `tests/unit/curated/test_machines_set_zone.py`, `test_tag_machine.py`, `test_untag_machine.py`

**Interfaces:**
- Consumes: `resolve_system_id` from Task 1.

- [ ] **Step 1: Write the failing tests**

- `machines_set_zone`: call with `zone="az1", hostname="node-1", confirm=True`; assert resolve GET then POST body `nodes=<resolved>`. Existing tests use `nodes=` keyword — must keep passing.
- `tag_machine`/`untag_machine`: add test `system_id="aa1"` path skips the hostname lookup (assert the `/machines/?hostname=` route NOT called) and tags `aa1` — this is new behavior; today the param doesn't exist.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/curated/test_machines_set_zone.py tests/unit/curated/test_tag_machine.py tests/unit/curated/test_untag_machine.py -v`
Expected: FAIL — unexpected keyword argument / missing param

- [ ] **Step 3: Implement**

`machines_set_zone.py`:

```python
        nodes: Annotated[
            str | None,
            Field(description="The system_id of the machine. Provide this or hostname, exactly one."),
        ] = None,
        *,
        hostname: Annotated[
            str | None,
            Field(description="Exact hostname; resolved to system_id server-side."),
        ] = None,
        confirm: Annotated[...] = False,
```

After confirm gate: `nodes = await resolve_system_id(client, nodes, hostname)`. Update the stale description sentence — delete "resolve hostnames with list_machines or get_machine first", replace with `"Accepts system_id (nodes) or hostname (provide exactly one). "`.

`tag_machine.py` / `untag_machine.py`: keep `hostname` (now optional), add optional `system_id`, delete the private inline lookup, and call `system_id = await resolve_system_id(client, system_id, hostname)` after the confirm gate. Existing tests pass `hostname` by keyword — keep passing.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/curated/test_machines_set_zone.py tests/unit/curated/test_tag_machine.py tests/unit/curated/test_untag_machine.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/maasmcp/curated/ tests/unit/curated/
git commit -m "feat: zone/tag ops share the resolver; machines_set_zone and tag ops accept either id form"
```

---

### Task 8: Registry guard test (completeness backstop)

**Files:**
- Test: `tests/unit/test_registry.py` (append)

**Interfaces:**
- Consumes: `ALL_TOOLS` from `maasmcp.curated._common` (already exported).

- [ ] **Step 1: Write the guard test**

```python
import inspect

from maasmcp.curated._common import ALL_TOOLS

# Param names that must be paired so no machine-addressed tool can silently
# stay system_id-only. values = the sibling param that must also exist.
DUAL_ADDRESSING_PAIRS = {
    "system_id": "hostname",
    "system_ids": "hostnames",
    "nodes": "hostname",      # machines_set_zone
    "machines": "hostnames",  # machines_accept
}


def test_machine_addressing_params_are_paired_with_hostname():
    offenders: dict[str, list[str]] = {}
    for cls in ALL_TOOLS:
        params = inspect.signature(cls().run).parameters
        for source, sibling in DUAL_ADDRESSING_PAIRS.items():
            if source in params and sibling not in params:
                offenders.setdefault(cls.name, []).append(f"{source} lacks {sibling}")
    assert not offenders, (
        "machine-addressed tools missing their hostname sibling: "
        + "; ".join(f"{t}: {', '.join(m)}" for t, m in offenders.items())
    )
```

- [ ] **Step 2: Run it**

Run: `uv run pytest tests/unit/test_registry.py -v`
Expected: PASS (if it fails, the named tools got skipped in Tasks 3–7 — go back and fix the named files; that's the point of the guard)

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_registry.py
git commit -m "test: registry guard — every system_id param must be paired with hostname"
```

---

### Task 9: Docs, full suite, release note

**Files:**
- Modify: `CHANGELOG.md`, `README.md`

- [ ] **Step 1: CHANGELOG entry** under a new `## [Unreleased]` heading (follow the file's existing entry style):

```markdown
## [Unreleased]

### Added
- All 62 machine-addressed tools now accept `hostname` in addition to `system_id`
  (provide exactly one; both set must agree). Bulk ops and `machines_accept` take
  a `hostnames` list resolved with a single fleet fetch. `machines_set_zone`
  (`nodes`), `tag_machine`, and `untag_machine` join the shared resolver.
  Backwards compatible: `system_id` merely became optional.
```

- [ ] **Step 2: README** — in the tools table/notes section, add one line: "All tools that target a machine accept either `system_id` or `hostname` (exactly one); hostname is resolved server-side."

- [ ] **Step 3: Full suite**

Run: `uv run pytest -x -q`
Expected: all PASS. Also run the linter the repo uses if configured (`uv run ruff check src tests` — check pyproject for a ruff config first; skip if absent).

- [ ] **Step 4: Commit**

```bash
git add CHANGELOG.md README.md
git commit -m "docs: hostname addressing on all machine tools (changelog + readme)"
```
