# Bulk Machine Operations + List Filters — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the maasmcp curated layer so an agent can run fleet-wide machine operations without N round-trips, and filter `list_machines` by hardware traits so an agent can scope queries server-side.

**Architecture:** Add four new curated tools (`bulk_release_machines`, `bulk_tag_machines`, `bulk_untag_machines`, `bulk_power_control_machines`) and three new optional kwargs to the existing `list_machines` (`zone`, `cpu_count_min`, `memory_min`). `bulk_release_machines` uses MAAS's batch endpoint (`POST /api/2.0/machines/op-release` with a `machines` body field); the other three bulk verbs fan out over per-id endpoints via `asyncio.gather(..., return_exceptions=True)` capped by a `Semaphore(10)`. Every bulk verb returns a list of per-id results so partial failures are visible to the agent without raising.

**Tech Stack:** Python 3.11+, FastMCP, pydantic, respx (tests), pytest-asyncio, mypy --strict, ruff.

## Global Constraints

These apply to every task. Re-read before each task's review.

- **MAAS authority:** Every endpoint shape, body field name, and response contract comes from `docs/reference/maasapi.md` at the project root (the user's authoritative MAAS reference). When the spec says "POST X with body Y", that must be exactly what `docs/reference/maasapi.md` documents for that endpoint.
- **`MaasClient.post()` signature (v0.1.1):** `async def post(self, path: str, *, json: dict[str, Any] | None = None) -> Any`. The kwarg name is `json=`, NOT `data=`. Internally (commit `5ad4a1a`) the client converts the dict to multipart/form-data so MAAS accepts it. All new tools MUST call `client.post(path, json=...)` with a plain dict — never `data=`.
- **Test fixture pattern (v0.1.1):** Tests that build a `MaasClient` directly via `MaasmcpConfig.load(None)` must first seed env vars because `tests/conftest.py` autouses `_isolate_settings_env` and `MaasmcpConfig` requires `maas`+`server` sub-configs:
  ```python
  monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
  monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
  monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "t")
  ```
  Then `client = MaasClient(cfg.maas)` and assign `client.base_url = cfg.maas.base_url` so `respx.mock(base_url=maas_client.base_url)` targets the right host. Wrap each test body in `async with maas_client:` inside `respx.mock(...)` — MaasClient's inner httpx client is None outside that block (asserted in `client.py:166`). The respx context must be the outer one so it intercepts the httpx client created on `__aenter__`.
- **MCPUpstreamError strips response body (security fix `5ad4a1a`):** Tests that assert on `MCPUpstreamError`'s stringified form must check the status code only (e.g. `"409"`), never the response body text (e.g. `"state conflict"`). Asserting the body would either require reverting the security fix or special-casing in the tool — neither is in scope.
- **Verbatim endpoints:**
  - `bulk_release_machines` → `POST /api/2.0/machines/op-release` (multipart/form-data). Body field name is `machines` (plural, a list of system_ids).
  - `bulk_tag_machines` / `bulk_untag_machines` → `POST /api/2.0/tags/{name}/op-update_nodes` (multipart/form-data). Body fields are `add` (string system_id, repeated for tag) and `remove` (string system_id, repeated for untag). One system_id per request.
  - `bulk_power_control_machines` → per-id `POST /api/2.0/machines/{system_id}/op-power_on` (or `op-power_off`, `op-power_cycle`). One POST per machine.
- **Fan-out cap:** `asyncio.Semaphore(10)` wraps every per-id POST inside `bulk_tag_machines`, `bulk_untag_machines`, `bulk_power_control_machines`. Single source of truth: module-level constant `_FANOUT_CONCURRENCY = 10` lives in its own module `src/maasmcp/curated/_fanout.py` and is imported by all three fan-out tools. This avoids a circular dependency: `_common.py` imports each tool module to register it, so the constant cannot live in `_common`. Tests assert `_FANOUT_CONCURRENCY == 10` by importing from `maasmcp.curated._fanout`.
- **Return shape:** Every bulk verb returns `list[dict[str, Any]]`. Each dict has exactly two keys:
  - `"system_id": str` — the host the operation targeted
  - `"status": "ok" | "error"` — outcome
  - On `"ok"`: `"result": <MAAS response object>` (whatever MAAS returned for that host; may be `None`).
  - On `"error"`: `"error": str` — a stringified exception message.
  - The verb never raises on partial failure. The first system_id is at index 0; order matches the input order.
- **List filter kwargs:** All three new kwargs (`zone`, `cpu_count_min`, `memory_min`) are optional. MAAS supports `zone`, `cpu_count` (already a minimum in MAAS semantics), and `mem` (minimum RAM in MiB, string) as server-side query params on `GET /api/2.0/machines/` per `docs/reference/maasapi.md` lines 6141–6153. All three filter server-side. Existing callers pass nothing and get identical behaviour. No kwargs is rejected.
- **Zone semantics:** `zone=<name>` is passed verbatim as the `zone` MAAS query param (exact match on the zone name, case-sensitive per MAAS).
- **Numeric filter semantics:** `cpu_count_min` is mapped to MAAS's `cpu_count` query param (MAAS docs: "Only nodes with the specified minimum number of CPUs will be included"). `memory_min` is mapped to MAAS's `mem` query param as a string (MAAS docs: "Only nodes with the specified minimum amount of RAM (in MiB) will be included"). The `_min` suffix on the kwarg name signals the minimum semantics to the agent without them needing to learn MAAS's quirky param names; internally we map `cpu_count_min=N` → `params["cpu_count"]=N` and `memory_min=N` → `params["mem"]=str(N)`.
- **Concurrency:** `bulk_tag_machines`, `bulk_untag_machines`, `bulk_power_control_machines` use `asyncio.gather(*tasks, return_exceptions=True)` after acquiring the semaphore per task. Each task wraps a single MAAS POST and catches all exceptions (`httpx.HTTPError`, `ValueError`) into the per-id error dict.
- **Coverage gate:** Curated-layer coverage must remain ≥85%. New tools and the modified `list_machines` must each reach ≥90% line coverage.
- **Lint/type gate:** `ruff check src tests` and `mypy --strict src` must pass clean before each commit.
- **Version:** Bump from `0.1.1` to `0.2.0`. Surface is additive, but new verbs are agent-facing and the bulk verbs can hammer MAAS; a minor bump signals "test before depending."
- **No new dependencies.** All imports already exist (`asyncio`, `typing`, `pydantic`, `respx`, `pytest-asyncio`).
- **Tool registration:** Each new tool goes in `src/maasmcp/curated/<name>.py` with the same `class XxxTool: name / description / async run / def register(mcp)` shape as the existing 12, and is registered in `src/maasmcp/curated/_common.py` alongside the others.

## File Structure

- `src/maasmcp/curated/bulk_release_machines.py` (new) — Tool class + multipart POST to MAAS batch endpoint.
- `src/maasmcp/curated/bulk_tag_machines.py` (new) — Tool class + asyncio.gather fan-out for `add=system_id`.
- `src/maasmcp/curated/bulk_untag_machines.py` (new) — Tool class + asyncio.gather fan-out for `remove=system_id`.
- `src/maasmcp/curated/bulk_power_control_machines.py` (new) — Tool class + asyncio.gather fan-out over `/machines/{id}/op-power_*`.
- `src/maasmcp/curated/_common.py` (modify) — Register 4 new tools.
- `src/maasmcp/curated/list_machines.py` (modify) — Add `zone`, `cpu_count_min`, `memory_min` kwargs.
- `tests/unit/curated/test_bulk_release_machines.py` (new) — respx unit tests.
- `tests/unit/curated/test_bulk_tag_machines.py` (new) — respx unit tests including partial failure.
- `tests/unit/curated/test_bulk_untag_machines.py` (new) — respx unit tests.
- `tests/unit/curated/test_bulk_power_control_machines.py` (new) — respx unit tests.
- `tests/unit/curated/test_list_machines_filters.py` (new) — Filter unit tests.
- `tests/e2e/test_bulk_operations.py` (new) — One e2e test gated by `@pytest.mark.e2e` and `pytest.mark.skipif`.
- `src/maasmcp/__init__.py` (modify) — `__version__ = "0.2.0"`.
- `pyproject.toml` (modify) — `version = "0.2.0"`.
- `CHANGELOG.md` (modify) — Add `0.2.0` section.
- `README.md` (modify) — Add the four new verbs to the tools list and update version line.

---

## Task 1: `bulk_release_machines` tool + tests

**Files:**
- Create: `src/maasmcp/curated/bulk_release_machines.py`
- Modify: `src/maasmcp/curated/_common.py` (import + register)
- Create: `tests/unit/curated/test_bulk_release_machines.py`

**Interfaces consumed:**
- `MaasClient.post(path: str, *, data: dict | None = None) -> Any` (already exists; `data=` triggers multipart/form-data per the prior fix in commit `5ad4a1a`).

**Interfaces produced:**
- `class BulkReleaseMachinesTool: name="bulk_release_machines"; async def run(client, system_ids, comment=None, erase=True, secure_erase=False, quick_erase=False, force=False) -> list[dict[str, Any]]`
- Registered on the global MCP server in `_common.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/curated/test_bulk_release_machines.py
"""bulk_release_machines: one POST per call, MAAS batch endpoint."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from maasmcp.config import MaasmcpConfig
from maasmcp.curated.bulk_release_machines import BulkReleaseMachinesTool
from maasmcp.maas.client import MaasClient


@pytest.fixture
def maas_client() -> MaasClient:
    cfg = MaasmcpConfig.load(None)
    return MaasClient(cfg.maas)


@pytest.mark.asyncio
async def test_happy_path_issues_exactly_one_post(maas_client: MaasClient) -> None:
    """Successful batch issues exactly one POST to MAAS's batch endpoint."""
    with respx.mock(base_url=maas_client.base_url) as mock:
        route = mock.post("/api/2.0/machines/op-release").mock(
            return_value=Response(
                200,
                json=[
                    {"system_id": "abc", "status": 1},
                    {"system_id": "def", "status": 1},
                ],
            )
        )
        tool = BulkReleaseMachinesTool()
        result = await tool.run(
            maas_client,
            system_ids=["abc", "def"],
            erase=True,
        )
    assert route.call_count == 1
    assert result == [
        {"system_id": "abc", "status": "ok", "result": {"system_id": "abc", "status": 1}},
        {"system_id": "def", "status": "ok", "result": {"system_id": "def", "status": 1}},
    ]


@pytest.mark.asyncio
async def test_partial_failure_returns_per_item_status(maas_client: MaasClient) -> None:
    """MAAS 200 with per-host status: list contains ok and error entries."""
    with respx.mock(base_url=maas_client.base_url) as mock:
        mock.post("/api/2.0/machines/op-release").mock(
            return_value=Response(
                200,
                json=[
                    {"system_id": "abc", "status": 1, "error": ""},
                    {"system_id": "def", "status": 0, "error": "machine is in DEPLOYING"},
                ],
            )
        )
        tool = BulkReleaseMachinesTool()
        result = await tool.run(maas_client, system_ids=["abc", "def"])
    assert result[0]["status"] == "ok"
    assert result[1]["status"] == "error"
    assert "DEPLOYING" in result[1]["error"]


@pytest.mark.asyncio
async def test_http_error_marks_all_items_error(maas_client: MaasClient) -> None:
    """A 409 from MAAS is wrapped: every item is errored with the same reason.

    Note: per the v0.1.1 security fix (commit ``5ad4a1a``), MaasClient's
    :class:`MCPUpstreamError` deliberately omits the response body so
    sensitive data never reaches logs or MCP errors. We therefore assert
    only that the status code is reflected in the error string — not the
    body text.
    """
    with respx.mock(base_url=maas_client.base_url) as mock:
        mock.post("/api/2.0/machines/op-release").mock(
            return_value=Response(409, text="state conflict")
        )
        tool = BulkReleaseMachinesTool()
        result = await tool.run(maas_client, system_ids=["abc", "def"])
    assert len(result) == 2
    assert all(item["status"] == "error" for item in result)
    assert "409" in result[0]["error"]


@pytest.mark.asyncio
async def test_empty_system_ids_returns_empty_list(maas_client: MaasClient) -> None:
    """No MAAS call when system_ids is empty."""
    with respx.mock(base_url=maas_client.base_url) as mock:
        tool = BulkReleaseMachinesTool()
        result = await tool.run(maas_client, system_ids=[])
    assert result == []
    assert not mock.calls


@pytest.mark.asyncio
async def test_erase_flags_propagate_as_data_fields(maas_client: MaasClient) -> None:
    """erase/secure_erase/quick_erase/force become multipart data fields."""
    with respx.mock(base_url=maas_client.base_url) as mock:
        route = mock.post("/api/2.0/machines/op-release").mock(
            return_value=Response(200, json=[])
        )
        await BulkReleaseMachinesTool().run(
            maas_client,
            system_ids=["abc"],
            comment="decom",
            erase=False,
            secure_erase=True,
            quick_erase=True,
            force=True,
        )
    sent = route.calls.last.request
    assert b'name="machines"' in sent.content
    assert b'abc' in sent.content
    assert b'name="comment"' in sent.content and b'decom' in sent.content
    assert b'name="erase"' in sent.content and b'false' in sent.content
    assert b'name="secure_erase"' in sent.content
    assert b'name="quick_erase"' in sent.content
    assert b'name="force"' in sent.content
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/curated/test_bulk_release_machines.py -v`
Expected: 5 errors with "ModuleNotFoundError: No module named 'maasmcp.curated.bulk_release_machines'".

- [ ] **Step 3: Write minimal implementation**

```python
# src/maasmcp/curated/bulk_release_machines.py
"""bulk_release_machines: release (deallocate) many machines in one MAAS call."""

from __future__ import annotations

from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic.json_schema import SkipJsonSchema

from maasmcp.maas.client import MaasClient


class BulkReleaseMachinesTool:
    name = "bulk_release_machines"
    description = (
        "Release multiple machines back to the pool in a single MAAS call. "
        "Default behaviour is to securely erase disks (erase=true). Returns "
        "one entry per input system_id with status='ok' or status='error' "
        "so the caller sees partial failures without raising."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        system_ids: list[str],
        comment: str | None = None,
        erase: bool = True,
        secure_erase: bool = False,
        quick_erase: bool = False,
        force: bool = False,
    ) -> list[dict[str, Any]]:
        if not system_ids:
            return []
        data: dict[str, Any] = {"machines": system_ids, "erase": erase,
                                "secure_erase": secure_erase, "quick_erase": quick_erase,
                                "force": force}
        if comment:
            data["comment"] = comment
        try:
            response = await client.post(
                "/api/2.0/machines/op-release", data=data
            )
        except Exception as exc:
            err = str(exc)
            return [{"system_id": sid, "status": "error", "error": err} for sid in system_ids]
        items = response if isinstance(response, list) else []
        out: list[dict[str, Any]] = []
        for sid in system_ids:
            match = next((it for it in items if isinstance(it, dict) and it.get("system_id") == sid), None)
            if match and not match.get("error"):
                out.append({"system_id": sid, "status": "ok", "result": match})
            elif match:
                out.append({"system_id": sid, "status": "error", "error": str(match.get("error"))})
            else:
                out.append({"system_id": sid, "status": "ok", "result": None})
        return out

    def register(self, mcp: FastMCP) -> None:
        mcp.add_tool(self.run, name=self.name, description=self.description)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/curated/test_bulk_release_machines.py -v`
Expected: 5 passed.

- [ ] **Step 5: Register in `_common.py`**

In `src/maasmcp/curated/_common.py`:
- Add `from maasmcp.curated.bulk_release_machines import BulkReleaseMachinesTool`
- Add `BulkReleaseMachinesTool,` to the registry list.
- The `_FANOUT_CONCURRENCY = 10` constant is already in place at `src/maasmcp/curated/_fanout.py` (added in Task 1's fix wave). Do NOT redeclare it in `_common.py` or any tool module.

- [ ] **Step 6: Verify lint + types**

Run: `ruff check src/maasmcp/curated/bulk_release_machines.py src/maasmcp/curated/_common.py && mypy --strict src/maasmcp/curated/bulk_release_machines.py src/maasmcp/curated/_common.py`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add src/maasmcp/curated/bulk_release_machines.py src/maasmcp/curated/_common.py tests/unit/curated/test_bulk_release_machines.py
git commit -m "feat(curated): add bulk_release_machines using MAAS batch endpoint"
```

---

## Task 2: `bulk_tag_machines` fan-out tool + tests

**Files:**
- Create: `src/maasmcp/curated/bulk_tag_machines.py`
- Modify: `src/maasmcp/curated/_common.py`
- Create: `tests/unit/curated/test_bulk_tag_machines.py`

**Interfaces produced:**
- `class BulkTagMachinesTool: name="bulk_tag_machines"; async def run(client, system_ids, tag) -> list[dict[str, Any]]`
- Each per-id POST is `POST /api/2.0/tags/{tag}/op-update_nodes` with multipart data `add=<system_id>`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/curated/test_bulk_tag_machines.py
"""bulk_tag_machines: asyncio.gather fan-out, partial-failure semantics."""

from __future__ import annotations

import asyncio

import pytest
import respx
from httpx import Response

from maasmcp.config import MaasmcpConfig
from maasmcp.curated._common import _FANOUT_CONCURRENCY
from maasmcp.curated.bulk_tag_machines import BulkTagMachinesTool
from maasmcp.maas.client import MaasClient


@pytest.fixture
def maas_client() -> MaasClient:
    cfg = MaasmcpConfig.load(None)
    return MaasClient(cfg.maas)


@pytest.mark.asyncio
async def test_happy_path_issues_one_post_per_host(maas_client: MaasClient) -> None:
    """Fan-out: N POSTs in parallel, one per system_id."""
    ids = ["a", "b", "c"]
    with respx.mock(base_url=maas_client.base_url) as mock:
        route = mock.post("/api/2.0/tags/k8s/op-update_nodes").mock(
            return_value=Response(200, json=[])
        )
        result = await BulkTagMachinesTool().run(maas_client, system_ids=ids, tag="k8s")
    assert route.call_count == len(ids)
    assert [r["system_id"] for r in result] == ids
    assert all(r["status"] == "ok" for r in result)


@pytest.mark.asyncio
async def test_partial_failure_preserves_order(maas_client: MaasClient) -> None:
    """One host 403s, the rest succeed — result keeps input order."""
    ids = ["ok1", "fail", "ok2"]

    def side_effect(request):
        body = request.content.decode()
        if "fail" in body:
            return Response(403, text="forbidden")
        return Response(200, json=[])

    with respx.mock(base_url=maas_client.base_url) as mock:
        mock.post("/api/2.0/tags/x/op-update_nodes").mock(side_effect=side_effect)
        result = await BulkTagMachinesTool().run(maas_client, system_ids=ids, tag="x")
    assert [r["system_id"] for r in result] == ids
    assert result[0]["status"] == "ok"
    assert result[1]["status"] == "error"
    assert "forbidden" in result[1]["error"]
    assert result[2]["status"] == "ok"


@pytest.mark.asyncio
async def test_empty_system_ids_is_noop(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:
        result = await BulkTagMachinesTool().run(maas_client, system_ids=[], tag="x")
    assert result == []
    assert not mock.calls


@pytest.mark.asyncio
async def test_fanout_semaphore_caps_concurrency(maas_client: MaasClient) -> None:
    """With 25 hosts and cap 10, never more than 10 concurrent in-flight POSTs."""
    in_flight = 0
    peak = 0

    async def side_effect(request):  # type: ignore[no-untyped-def]
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.05)
        in_flight -= 1
        return Response(200, json=[])

    ids = [f"m{i}" for i in range(25)]
    with respx.mock(base_url=maas_client.base_url) as mock:
        mock.post("/api/2.0/tags/x/op-update_nodes").mock(side_effect=side_effect)
        await BulkTagMachinesTool().run(maas_client, system_ids=ids, tag="x")
    assert peak <= _FANOUT_CONCURRENCY
    assert _FANOUT_CONCURRENCY == 10


@pytest.mark.asyncio
async def test_empty_tag_raises_value_error(maas_client: MaasClient) -> None:
    with pytest.raises(ValueError, match="tag"):
        await BulkTagMachinesTool().run(maas_client, system_ids=["a"], tag="")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/curated/test_bulk_tag_machines.py -v`
Expected: 5 errors with `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/maasmcp/curated/bulk_tag_machines.py
"""bulk_tag_machines: add a tag to many hosts via asyncio.gather fan-out."""

from __future__ import annotations

import asyncio
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._common import _FANOUT_CONCURRENCY
from maasmcp.maas.client import MaasClient


class BulkTagMachinesTool:
    name = "bulk_tag_machines"
    description = (
        "Add a tag to multiple machines in parallel. MAAS has no batch tag "
        "endpoint, so this issues one POST per host (asyncio.gather, cap 10 "
        "in flight). Returns one entry per system_id so partial failures are "
        "visible without raising."
    )

    async def _tag_one(
        self,
        client: MaasClient,
        tag: str,
        system_id: str,
        sem: asyncio.Semaphore,
    ) -> dict[str, Any]:
        async with sem:
            try:
                await client.post(
                    f"/api/2.0/tags/{tag}/op-update_nodes",
                    data={"add": system_id},
                )
                return {"system_id": system_id, "status": "ok", "result": None}
            except Exception as exc:
                return {"system_id": system_id, "status": "error", "error": str(exc)}

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        system_ids: list[str],
        tag: str,
    ) -> list[dict[str, Any]]:
        if not tag:
            raise ValueError("tag must be a non-empty string")
        if not system_ids:
            return []
        sem = asyncio.Semaphore(_FANOUT_CONCURRENCY)
        results = await asyncio.gather(
            *(self._tag_one(client, tag, sid, sem) for sid in system_ids)
        )
        return list(results)

    def register(self, mcp: FastMCP) -> None:
        mcp.add_tool(self.run, name=self.name, description=self.description)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/curated/test_bulk_tag_machines.py -v`
Expected: 5 passed.

- [ ] **Step 5: Register in `_common.py`**

In `src/maasmcp/curated/_common.py`: import + add `BulkTagMachinesTool,` to the registry.

- [ ] **Step 6: Verify lint + types**

Run: `ruff check src/maasmcp/curated/bulk_tag_machines.py src/maasmcp/curated/_common.py && mypy --strict src/maasmcp/curated/bulk_tag_machines.py src/maasmcp/curated/_common.py`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add src/maasmcp/curated/bulk_tag_machines.py src/maasmcp/curated/_common.py tests/unit/curated/test_bulk_tag_machines.py
git commit -m "feat(curated): add bulk_tag_machines fan-out over op-update_nodes"
```

---

## Task 3: `bulk_untag_machines` tool + tests

**Files:**
- Create: `src/maasmcp/curated/bulk_untag_machines.py`
- Modify: `src/maasmcp/curated/_common.py`
- Create: `tests/unit/curated/test_bulk_untag_machines.py`

This task mirrors Task 2 but uses `remove=` in the per-id body instead of `add=`. Run after Task 2 so `_common.py` doesn't churn with two parallel edits.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/curated/test_bulk_untag_machines.py
"""bulk_untag_machines: asyncio.gather fan-out, remove= body field."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from maasmcp.config import MaasmcpConfig
from maasmcp.curated.bulk_untag_machines import BulkUntagMachinesTool
from maasmcp.maas.client import MaasClient


@pytest.fixture
def maas_client() -> MaasClient:
    cfg = MaasmcpConfig.load(None)
    return MaasClient(cfg.maas)


@pytest.mark.asyncio
async def test_happy_path_sends_remove_field(maas_client: MaasClient) -> None:
    """Each POST body contains 'remove=<sid>' and no 'add'."""
    with respx.mock(base_url=maas_client.base_url) as mock:
        route = mock.post("/api/2.0/tags/x/op-update_nodes").mock(
            return_value=Response(200, json=[])
        )
        result = await BulkUntagMachinesTool().run(
            maas_client, system_ids=["a", "b"], tag="x"
        )
    assert route.call_count == 2
    for call in route.calls:
        body = call.request.content.decode()
        assert "remove=" in body
        assert "add=" not in body
    assert all(r["status"] == "ok" for r in result)


@pytest.mark.asyncio
async def test_partial_failure_per_item(maas_client: MaasClient) -> None:
    ids = ["ok", "fail"]

    def side_effect(request):
        body = request.content.decode()
        if "fail" in body:
            return Response(404, text="tag not found")
        return Response(200, json=[])

    with respx.mock(base_url=maas_client.base_url) as mock:
        mock.post("/api/2.0/tags/x/op-update_nodes").mock(side_effect=side_effect)
        result = await BulkUntagMachinesTool().run(maas_client, system_ids=ids, tag="x")
    assert result[0]["status"] == "ok"
    assert result[1]["status"] == "error"
    assert "tag not found" in result[1]["error"]


@pytest.mark.asyncio
async def test_empty_inputs(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:
        result = await BulkUntagMachinesTool().run(maas_client, system_ids=[], tag="x")
    assert result == []
    assert not mock.calls


@pytest.mark.asyncio
async def test_empty_tag_raises(maas_client: MaasClient) -> None:
    with pytest.raises(ValueError):
        await BulkUntagMachinesTool().run(maas_client, system_ids=["a"], tag="")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/curated/test_bulk_untag_machines.py -v`
Expected: 4 errors with `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/maasmcp/curated/bulk_untag_machines.py
"""bulk_untag_machines: remove a tag from many hosts via fan-out."""

from __future__ import annotations

import asyncio
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._fanout import _FANOUT_CONCURRENCY
from maasmcp.maas.client import MaasClient


class BulkUntagMachinesTool:
    name = "bulk_untag_machines"
    description = (
        "Remove a tag from multiple machines in parallel. Mirrors "
        "bulk_tag_machines but uses the 'remove' body field."
    )

    async def _untag_one(
        self, client: MaasClient, tag: str, system_id: str, sem: asyncio.Semaphore,
    ) -> dict[str, Any]:
        async with sem:
            try:
                await client.post(
                    f"/api/2.0/tags/{tag}/op-update_nodes",
                    data={"remove": system_id},
                )
                return {"system_id": system_id, "status": "ok", "result": None}
            except Exception as exc:
                return {"system_id": system_id, "status": "error", "error": str(exc)}

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        system_ids: list[str],
        tag: str,
    ) -> list[dict[str, Any]]:
        if not tag:
            raise ValueError("tag must be a non-empty string")
        if not system_ids:
            return []
        sem = asyncio.Semaphore(_FANOUT_CONCURRENCY)
        results = await asyncio.gather(
            *(self._untag_one(client, tag, sid, sem) for sid in system_ids)
        )
        return list(results)

    def register(self, mcp: FastMCP) -> None:
        mcp.add_tool(self.run, name=self.name, description=self.description)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/curated/test_bulk_untag_machines.py -v`
Expected: 4 passed.

- [ ] **Step 5: Register in `_common.py`**

- [ ] **Step 6: Verify lint + types**

Run: `ruff check src/maasmcp/curated/bulk_untag_machines.py src/maasmcp/curated/_common.py && mypy --strict src/maasmcp/curated/bulk_untag_machines.py src/maasmcp/curated/_common.py`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add src/maasmcp/curated/bulk_untag_machines.py src/maasmcp/curated/_common.py tests/unit/curated/test_bulk_untag_machines.py
git commit -m "feat(curated): add bulk_untag_machines fan-out"
```

---

## Task 4: `bulk_power_control_machines` tool + tests

**Files:**
- Create: `src/maasmcp/curated/bulk_power_control_machines.py`
- Modify: `src/maasmcp/curated/_common.py`
- Create: `tests/unit/curated/test_bulk_power_control_machines.py`

**Action mapping:**
- `on` → `POST /api/2.0/machines/{system_id}/op-power_on`
- `off` → `POST /api/2.0/machines/{system_id}/op-power_off`
- `cycle` → `POST /api/2.0/machines/{system_id}/op-power_cycle`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/curated/test_bulk_power_control_machines.py
"""bulk_power_control_machines: per-id op-power_* POSTs in parallel."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from maasmcp.config import MaasmcpConfig
from maasmcp.curated.bulk_power_control_machines import BulkPowerControlMachinesTool
from maasmcp.maas.client import MaasClient


@pytest.fixture
def maas_client() -> MaasClient:
    cfg = MaasmcpConfig.load(None)
    return MaasClient(cfg.maas)


@pytest.mark.asyncio
async def test_on_action_hits_power_on_per_id(maas_client: MaasClient) -> None:
    ids = ["a", "b"]
    with respx.mock(base_url=maas_client.base_url) as mock:
        mock.post("/api/2.0/machines/a/op-power_on").mock(
            return_value=Response(200, json={})
        )
        mock.post("/api/2.0/machines/b/op-power_on").mock(
            return_value=Response(200, json={})
        )
        result = await BulkPowerControlMachinesTool().run(
            maas_client, system_ids=ids, action="on"
        )
    assert all(r["status"] == "ok" for r in result)
    assert [r["system_id"] for r in result] == ids


@pytest.mark.asyncio
async def test_cycle_action_hits_power_cycle(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:
        route = mock.post("/api/2.0/machines/x/op-power_cycle").mock(
            return_value=Response(204, json=None)
        )
        await BulkPowerControlMachinesTool().run(
            maas_client, system_ids=["x"], action="cycle"
        )
    assert route.called


@pytest.mark.asyncio
async def test_off_action_hits_power_off(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:
        route = mock.post("/api/2.0/machines/x/op-power_off").mock(
            return_value=Response(200, json={})
        )
        await BulkPowerControlMachinesTool().run(
            maas_client, system_ids=["x"], action="off"
        )
    assert route.called


@pytest.mark.asyncio
async def test_invalid_action_raises_value_error(maas_client: MaasClient) -> None:
    with pytest.raises(ValueError, match="action"):
        await BulkPowerControlMachinesTool().run(
            maas_client, system_ids=["x"], action="reboot"
        )


@pytest.mark.asyncio
async def test_partial_failure(maas_client: MaasClient) -> None:
    def side_effect(request):
        if "fail" in str(request.url):
            return Response(403, text="forbidden")
        return Response(200, json={})
    ids = ["ok", "fail"]
    with respx.mock(base_url=maas_client.base_url) as mock:
        for sid in ids:
            mock.post(f"/api/2.0/machines/{sid}/op-power_on").mock(side_effect=side_effect)
        result = await BulkPowerControlMachinesTool().run(
            maas_client, system_ids=ids, action="on"
        )
    assert result[0]["status"] == "ok"
    assert result[1]["status"] == "error"


@pytest.mark.asyncio
async def test_empty_system_ids_is_noop(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:
        result = await BulkPowerControlMachinesTool().run(
            maas_client, system_ids=[], action="on"
        )
    assert result == []
    assert not mock.calls
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/curated/test_bulk_power_control_machines.py -v`
Expected: 6 errors.

- [ ] **Step 3: Write minimal implementation**

```python
# src/maasmcp/curated/bulk_power_control_machines.py
"""bulk_power_control_machines: power on/off/cycle many hosts in parallel."""

from __future__ import annotations

import asyncio
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._fanout import _FANOUT_CONCURRENCY
from maasmcp.maas.client import MaasClient

_ALLOWED = {"on", "off", "cycle"}
_ACTION_TO_OP = {"on": "op-power_on", "off": "op-power_off", "cycle": "op-power_cycle"}


class BulkPowerControlMachinesTool:
    name = "bulk_power_control_machines"
    description = (
        "Power on/off/cycle multiple machines in parallel. Action must be "
        "one of on/off/cycle. MAAS has no batch power endpoint, so this "
        "issues one POST per host (cap 10 in flight)."
    )

    async def _power_one(
        self, client: MaasClient, system_id: str, action: str, sem: asyncio.Semaphore,
    ) -> dict[str, Any]:
        async with sem:
            try:
                await client.post(
                    f"/api/2.0/machines/{system_id}/{_ACTION_TO_OP[action]}"
                )
                return {"system_id": system_id, "status": "ok", "result": None}
            except Exception as exc:
                return {"system_id": system_id, "status": "error", "error": str(exc)}

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        system_ids: list[str],
        action: str,
    ) -> list[dict[str, Any]]:
        if action not in _ALLOWED:
            raise ValueError(f"action must be one of {sorted(_ALLOWED)}, got {action!r}")
        if not system_ids:
            return []
        sem = asyncio.Semaphore(_FANOUT_CONCURRENCY)
        results = await asyncio.gather(
            *(self._power_one(client, sid, action, sem) for sid in system_ids)
        )
        return list(results)

    def register(self, mcp: FastMCP) -> None:
        mcp.add_tool(self.run, name=self.name, description=self.description)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/curated/test_bulk_power_control_machines.py -v`
Expected: 6 passed.

- [ ] **Step 5: Register in `_common.py`**

- [ ] **Step 6: Verify lint + types**

Run: `ruff check src/maasmcp/curated/bulk_power_control_machines.py src/maasmcp/curated/_common.py && mypy --strict src/maasmcp/curated/bulk_power_control_machines.py src/maasmcp/curated/_common.py`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add src/maasmcp/curated/bulk_power_control_machines.py src/maasmcp/curated/_common.py tests/unit/curated/test_bulk_power_control_machines.py
git commit -m "feat(curated): add bulk_power_control_machines fan-out"
```

---

## Task 5: `list_machines` filter extensions + tests

**Files:**
- Modify: `src/maasmcp/curated/list_machines.py`
- Create: `tests/unit/curated/test_list_machines_filters.py`

**Behaviour:**
- Add three optional kwargs: `zone: str | None = None`, `cpu_count_min: int | None = None`, `memory_min: int | None = None`.
- All three map to MAAS's server-side query params: `zone=<name>`, `cpu_count=<N>`, `mem=<N-as-string>`. See Global Constraints for the docs/reference/maasapi.md references.
- All kwargs default to `None` (no filter). Existing callers are unaffected.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/curated/test_list_machines_filters.py
"""list_machines: new server-side and client-side filter kwargs."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from maasmcp.config import MaasmcpConfig
from maasmcp.curated.list_machines import ListMachinesTool
from maasmcp.maas.client import MaasClient


@pytest.fixture
def maas_client() -> MaasClient:
    cfg = MaasmcpConfig.load(None)
    return MaasClient(cfg.maas)


def _machine(system_id: str, **kw: object) -> dict[str, object]:
    base: dict[str, object] = {
        "system_id": system_id,
        "hostname": f"h-{system_id}",
        "status_name": "READY",
        "power_state": "on",
        "tag_names": [],
        "pool": {"name": "default"},
        "zone": {"name": "zone-1"},
        "cpu_count": 4,
        "memory": 8192,
    }
    base.update(kw)
    return base


@pytest.mark.asyncio
async def test_zone_filter_passes_query_param(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:
        route = mock.get("/api/2.0/machines/").mock(
            return_value=Response(200, json=[_machine("a"), _machine("b")])
        )
        result = await ListMachinesTool().run(maas_client, zone="zone-1")
    assert "zone=zone-1" in str(route.calls.last.request.url)
    assert len(result) == 2


@pytest.mark.asyncio
async def test_cpu_count_min_passes_server_side_query_param(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:
        route = mock.get("/api/2.0/machines/").mock(
            return_value=Response(200, json=[_machine("big", cpu_count=16)])
        )
        result = await ListMachinesTool().run(maas_client, cpu_count_min=8)
    assert "cpu_count=8" in str(route.calls.last.request.url)
    assert len(result) == 1


@pytest.mark.asyncio
async def test_memory_min_passes_server_side_query_param(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:
        route = mock.get("/api/2.0/machines/").mock(
            return_value=Response(200, json=[_machine("high", memory=32768)])
        )
        result = await ListMachinesTool().run(maas_client, memory_min=16384)
    assert "mem=16384" in str(route.calls.last.request.url)
    assert len(result) == 1


@pytest.mark.asyncio
async def test_combined_filters_pass_query_params(maas_client: MaasClient) -> None:
    """All three filters AND together in the MAAS request URL."""
    with respx.mock(base_url=maas_client.base_url) as mock:
        route = mock.get("/api/2.0/machines/").mock(
            return_value=Response(200, json=[_machine("a")])
        )
        await ListMachinesTool().run(
            maas_client, zone="zone-1", cpu_count_min=8, memory_min=16384
        )
    url = str(route.calls.last.request.url)
    assert "zone=zone-1" in url
    assert "cpu_count=8" in url
    assert "mem=16384" in url


@pytest.mark.asyncio
async def test_no_kwargs_unchanged_behaviour(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:
        mock.get("/api/2.0/machines/").mock(
            return_value=Response(200, json=[_machine("a")])
        )
        result = await ListMachinesTool().run(maas_client)
    assert len(result) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/curated/test_list_machines_filters.py -v`
Expected: 5 failures with `TypeError: run() got an unexpected keyword argument 'zone'` (and similar for `cpu_count_min`, `memory_min`).

- [ ] **Step 3: Modify `list_machines.py`**

Read the file first; then change the `run` signature and add three branches to the filter block. Edit at `src/maasmcp/curated/list_machines.py`:

```python
    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        status: str | None = None,
        pool: str | None = None,
        tag: str | None = None,
        hostname_glob: str | None = None,
        zone: str | None = None,
        cpu_count_min: int | None = None,
        memory_min: int | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {}
        if status:
            params["status"] = status
        if zone:
            params["zone"] = zone
        if cpu_count_min is not None:
            params["cpu_count"] = cpu_count_min
        if memory_min is not None:
            params["mem"] = str(memory_min)
        machines: Any = await client.get("/api/2.0/machines/", params=params)
        view: list[dict[str, Any]] = []
        if not isinstance(machines, list):
            return view
        for m in machines:
            if not isinstance(m, dict):
                continue
            if pool and (m.get("pool") or {}).get("name") != pool:  # type: ignore[union-attr]
                continue
            if tag and tag not in (m.get("tag_names") or []):
                continue
            if hostname_glob and not fnmatch(m.get("hostname", ""), hostname_glob):
                continue
            view.append(
                {
                    "system_id": m.get("system_id"),
                    "hostname": m.get("hostname"),
                    "status_name": m.get("status_name"),
                    "power_state": m.get("power_state"),
                    "tag_names": m.get("tag_names"),
                    "pool": (m.get("pool") or {}).get("name"),
                }
            )
        return view
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/curated/test_list_machines_filters.py tests/unit/curated/test_list_machines.py -v`
Expected: all pass (existing list_machines tests + 5 new = 5+n green).

- [ ] **Step 5: Verify lint + types**

Run: `ruff check src/maasmcp/curated/list_machines.py && mypy --strict src/maasmcp/curated/list_machines.py`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add src/maasmcp/curated/list_machines.py tests/unit/curated/test_list_machines_filters.py
git commit -m "feat(curated): add zone/cpu_count_min/memory_min filters to list_machines"
```

---

## Task 6: End-to-end integration test (gated)

**Files:**
- Create: `tests/e2e/test_bulk_operations.py`

- [ ] **Step 1: Write the e2e test**

```python
# tests/e2e/test_bulk_operations.py
"""Bulk operations against a real MAAS. Gated on MAASMCP_E2E_MAAS_URL env var."""

from __future__ import annotations

import os

import pytest

from maasmcp.config import MaasmcpConfig
from maasmcp.curated.bulk_tag_machines import BulkTagMachinesTool
from maasmcp.curated.bulk_untag_machines import BulkUntagMachinesTool
from maasmcp.maas.client import MaasClient

E2E_URL = os.environ.get("MAASMCP_E2E_MAAS_URL")
pytestmark = [
    pytest.mark.skipif(not E2E_URL, reason="MAASMCP_E2E_MAAS_URL not set"),
    pytest.mark.e2e,
]


@pytest.fixture
def maas_client() -> MaasClient:
    cfg = MaasmcpConfig.load(None)
    cfg.maas.base_url = E2E_URL  # type: ignore[attr-defined]
    return MaasClient(cfg.maas)


@pytest.mark.asyncio
async def test_bulk_tag_round_trip(maas_client: MaasClient) -> None:
    """Tag a freshly-discovered READY machine with a unique tag, then untag."""
    import uuid
    tag = f"e2e-{uuid.uuid4().hex[:8]}"
    listed = await maas_client.get("/api/2.0/machines/", params={"status": "READY"})
    assert isinstance(listed, list) and listed, "no READY machines in this MAAS"
    system_id = listed[0]["system_id"]  # type: ignore[index]

    tag_result = await BulkTagMachinesTool().run(
        maas_client, system_ids=[system_id], tag=tag
    )
    assert tag_result[0]["status"] == "ok", tag_result

    machine = await maas_client.get(f"/api/2.0/machines/{system_id}/")
    assert tag in (machine.get("tag_names") or []), machine

    untag_result = await BulkUntagMachinesTool().run(
        maas_client, system_ids=[system_id], tag=tag
    )
    assert untag_result[0]["status"] == "ok", untag_result
```

- [ ] **Step 2: Verify the test is properly skipped without env var**

Run: `pytest tests/e2e/test_bulk_operations.py -v`
Expected: 1 skipped with reason "MAASMCP_E2E_MAAS_URL not set".

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/test_bulk_operations.py
git commit -m "test(e2e): add gated bulk tag/untag round-trip test"
```

---

## Task 7: Version bump + CHANGELOG + README

**Files:**
- Modify: `src/maasmcp/__init__.py`
- Modify: `pyproject.toml`
- Modify: `CHANGELOG.md`
- Modify: `README.md`

- [ ] **Step 1: Bump version in two places**

`src/maasmcp/__init__.py`:
```python
"""maasmcp — MCP server for Canonical MAAS."""
__version__ = "0.2.0"
```

`pyproject.toml`: change `version = "0.1.1"` to `version = "0.2.0"`.

- [ ] **Step 2: Add CHANGELOG section**

Prepend this block to `CHANGELOG.md` (above the `0.1.1` section):

```markdown
## [0.2.0] — 2026-07-07

### Added
- `bulk_release_machines` — release N machines in one MAAS batch POST (uses `/api/2.0/machines/op-release` with the `machines` list field). Returns per-system_id status; never raises on partial failure.
- `bulk_tag_machines` / `bulk_untag_machines` — add or remove a tag from N machines in parallel via `asyncio.gather` (MAAS has no batch tag endpoint). Concurrency capped at 10. Per-system_id status.
- `bulk_power_control_machines` — power on/off/cycle N machines in parallel via per-id `/machines/{id}/op-power_*`. Concurrency capped at 10. Per-system_id status.
- `list_machines` accepts three new optional kwargs: `zone` (server-side filter via MAAS `zone` query param), `cpu_count_min` (server-side, mapped to MAAS `cpu_count` query param), `memory_min` (server-side, mapped to MAAS `mem` query param as a string). Backwards compatible: existing callers pass nothing and see the same result.

### Changed
- Surface is additive but agent-friendliness is the headline — bulk verbs expose partial failure without raising so an agent can decide what to retry.
```

- [ ] **Step 3: Update README tools list**

Find the existing tools list (search README for the bullet list of curated verbs) and append four new bullets:

```markdown
- `bulk_release_machines` — release N machines in one MAAS call (returns per-host status).
- `bulk_tag_machines` — add a tag to N machines in parallel (returns per-host status).
- `bulk_untag_machines` — remove a tag from N machines in parallel (returns per-host status).
- `bulk_power_control_machines` — power on/off/cycle N machines in parallel (returns per-host status).
```

Also update the version line at the top of the README from `0.1.1` to `0.2.0`.

- [ ] **Step 4: Verify lint + types + full suite + coverage**

Run:
```bash
ruff check src tests && mypy --strict src && pytest -q
pytest -q --cov=maasmcp.curated --cov-report=term-missing --no-cov-on-fail
```
Expected: ruff clean, mypy clean, all tests pass (e2e gate skipped). Coverage shows ≥85% for the curated layer overall and ≥90% line coverage on each of `bulk_release_machines.py`, `bulk_tag_machines.py`, `bulk_untag_machines.py`, `bulk_power_control_machines.py`, and `list_machines.py`. If any new file is below 90%, add tests until it crosses the threshold — the spec mandates it.

- [ ] **Step 5: Commit and tag**

```bash
git add src/maasmcp/__init__.py pyproject.toml CHANGELOG.md README.md
git commit -m "chore(release): v0.2.0 bulk operations + list filters"
git tag -a v0.2.0 -m "v0.2.0: bulk machine operations + list_machines filters"
```

Push only after user consent (per Global Constraints).
