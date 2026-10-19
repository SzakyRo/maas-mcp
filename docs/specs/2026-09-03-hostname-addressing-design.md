# Design: Dual system_id/hostname addressing on all machine tools

**Date:** 2026-09-03
**Status:** Approved (design), pending implementation plan

## Problem

The MAAS REST API addresses machines strictly by `system_id` (a required path
parameter on ~50 endpoints); `hostname` exists upstream only as a list filter
(`GET /machines/?hostname=...`) and as the `name` constraint on the allocate op.

The MCP mirrors this unevenly:

- `get_machine` accepts either (dual-probe, handles base-36/hex ambiguity).
- `tag_machine` / `untag_machine` take `hostname` and resolve privately
  (duplicated ~6-line lookup in each).
- `acquire_machine` matches a hostname client-side, allocates by system_id.
- Every other machine-addressed tool — **62 tools** including all storage,
  network, power, deploy, release, and bulk verbs — is strict `system_id`.
  `machines_set_zone` explicitly punts ("resolve hostnames with list_machines
  or get_machine first"), forcing a chained lookup call.

Callers (LLM agents especially) address machines by hostname naturally
(`autodeploy-pve-02`), and a partially-consistent surface is where hallucinated
calls come from ("tag_machine took a hostname, so machine_delete probably does
too"). Goal: **every tool that targets a machine accepts `system_id` or
`hostname`, uniformly.**

## Decisions (trade-offs considered)

| Decision | Chosen | Rejected | Why |
|---|---|---|---|
| Schema shape | **Additive** optional `hostname` beside `system_id` | Rename all to `identifier` | Renames break every cached MCP tool schema and every existing named-argument call. Additive is invisible to existing clients; required→optional is non-breaking. |
| Collision handling | Explicit error on conflict | Silent precedence | On destructive verbs (release, delete_raid) "which machine did it mean?" must never be a heuristic. |
| system_id existence pre-check | **None** (trust + let MAAS error) | Verify with a GET first | Doubles API round-trips on every op; MAAS's own 404 surfaces on the real call anyway. `get_machine` keeps its probe logic (read-only, wrong guess costs one call). |
| Bulk resolution | **One** list fetch + in-memory map | N per-hostname lookups | `/machines/?hostname=` is one request per host; a single unpaginated `GET /machines/` amortizes across the fleet. |
| Coverage | **All** 62 machine-addressed tools | Only the verbs typically driven by name | Partial consistency invites schema hallucination; per-tool change is the same mechanical shape either way, so uniformity is mostly free. |

## Design

### 1. Shared resolver: `src/maasmcp/curated/_resolve.py`

New module owned by the curated layer:

```python
async def resolve_system_id(
    client: MaasClient,
    system_id: str | None,
    hostname: str | None,
) -> str:
```

Semantics:

- **Both None** → `ValueError("must provide exactly one of system_id or hostname")`.
- **`system_id` only** → returned unchanged, no upstream call.
- **`hostname` only** → `GET /api/2.0/machines/?hostname=<exact>`; MAAS
  exact-matches this filter. Empty result →
  `ValueError("no machine found with hostname ...")`. First hit's `system_id`
  returned. If MAAS ever returns >1 (shouldn't — hostnames are unique), take
  `[0]` as tag_machine does today.
- **Both set** → perform the hostname lookup; if its `system_id` differs →
  `ValueError` naming both values; matching → return it.

`get_machine`'s dual-probe (base-36/hex-hostname ambiguity) stays where it is
— it answers "fetch me a record", not "resolve me an id". The resolver does
not need ambiguity handling: hostname is always queried via the filter,
system_id is always trusted.

### 2. Per-tool change (the 62)

Each tool gets the identical mechanical edit:

```python
system_id: Annotated[str | None, Field(
    description="MAAS system_id of the machine (e.g. 'abc123'). "
    "Provide this or hostname, exactly one.")] = None,
hostname: Annotated[str | None, Field(
    description="Exact hostname of the machine; resolved to system_id "
    "server-side.")] = None,
```

- `system_id` changes from required to optional. JSON-schema-wise the
  `required` list loses one entry; no renames, no type changes.
- After existing confirm/validation gates: `system_id = await
  resolve_system_id(client, system_id, hostname)`.
- Confirm-gate error messages include hostname when given (auditability of the
  rejected-without-confirm path).
- Tool descriptions gain one sentence: "Accepts `system_id` or `hostname`
  (provide exactly one)."

### 3. Special cases

- **Bulk ops (4):** `bulk_tag_machines`, `bulk_untag_machines`,
  `bulk_power_control_machines`, `bulk_release_machines` add
  `hostnames: list[str] | None` beside `system_ids: list[str] | None`
  (which becomes optional). Resolution: one `GET /api/2.0/machines/`, build a
  hostname→system_id map in memory, resolve the whole list, append to
  system_ids. Unmatched hostnames yield per-host `{"status": "error",
  "error": "no machine found with hostname ..."}` entries — consistent with
  existing per-host error semantics. Both-lists-empty → `ValueError`.
- **`machines_set_zone`:** gains optional `hostname` beside `nodes`; unchanged
  upstream call.
- **`machines_accept`:** `machines` (list of system_ids) becomes optional;
  gains `hostnames: list[str] | None`, resolved via the bulk map helper.
- **`tag_machine`/`untag_machine`:** keep `hostname`, add optional
  `system_id`; delete their private lookups, call the shared resolver.
- **`get_machine`:** unchanged (already dual-accept via `identifier`).

### 4. Bulk-map helper

`resolve_hostnames(client, hostnames: list[str]) -> tuple[dict[str, str], list[str]]`
in `_resolve.py`: one fleet list call, returns (hostname→id map, unmatched
list). Used by the four bulk ops and `machines_accept`.

### 5. Testing

- **`tests/unit/curated/test_resolve.py`** — resolver unit tests against the
  existing mocked client: neither set; system_id only (no HTTP touched);
  hostname only hit/miss; both-match; both-conflict; bulk map with partial
  match.
- **Registry guard (`tests/unit/test_registry.py`):** iterate `ALL_TOOLS`,
  assert every tool schema exposing `system_id` also exposes `hostname`, and
  every schema exposing `system_ids` also exposes `hostnames`. This is the
  proof the 62-tool sweep is complete and stays complete.
- **Representative behavior tests** (mocked client, existing style): one
  storage verb, one bulk op, `machines_set_zone`, `tag_machine` — each called
  with `hostname` must resolve then issue the byte-identical upstream request
  the `system_id` path makes. Existing tests keep passing untouched (schema is
  a superset).
- e2e: no new e2e required; existing e2e passes `system_id` and exercises the
  compatibility path.

### 6. Docs / versioning

- `CHANGELOG.md`: new minor-version entry describing the additive surface.
- README tool table: one-line note "all machine tools accept system_id or
  hostname".
- No renames, no removals, no fan-out/concurrency changes.

## Risks

- **Schema-size growth:** +1 string field on 62 tools. Trivial vs. the benefit.
- **Hostname uniqueness assumption:** MAAS enforces unique hostnames per
  domain; first-hit logic matches existing tag_machine behavior. Documented in
  resolver docstring.
- **Live-MAAS quirk:** the user's MAAS serves `/machines/` unpaginated — the
  bulk map assumes the full list in one call, already true per memory note;
  add pagination guard via existing client paginate flag if the helper is
  reused elsewhere later.
