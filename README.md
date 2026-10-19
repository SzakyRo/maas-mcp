# maasmcp

> **An MCP server that puts [Canonical MAAS](https://maas.io/) bare-metal provisioning in the hands of LLM agents — safely, type-checkedly, and without writing a curl one-liner ever again.**

`maasmcp` speaks the [Model Context Protocol](https://modelcontextprotocol.io/) over streamable-HTTP and exposes the **MAAS 3.7** API to any MCP-aware client (Claude Code, Cursor, custom agents) as a single, fully hand-written surface:

**126 hand-written tools** — opinionated, type-checked, safety-gated. High-level workflow verbs (`acquire_machine`, `deploy_machine`, `apply_storage_layout`, `network_layout`, `bulk_power_control_machines`, …) for the jobs you actually do, plus direct per-resource tools (`machines_create`, `tag_update`, `user_delete`, …) for everything else. Every tool is a small class with `name`, `description`, and `run`, Pydantic-`Field`-documented parameters, and a `confirm` gate on every destructive write. Each tool also publishes MCP `ToolAnnotations` (`title`, `readOnlyHint`, `destructiveHint`, `idempotentHint`) and a leading `[domain]` tag in its description, so clients can navigate the surface without memorizing 126 names.

Current version: **0.10.1** · License: **Apache-2.0** · Python: **≥ 3.11**

---

## Table of contents

- [Why maasmcp?](#why-maasmcp)
- [Architecture](#architecture)
- [Quickstart](#quickstart)
- [Configuration](#configuration)
- [Tools](#tools)
  - [High-level workflow verbs](#high-level-workflow-verbs)
  - [Direct MAAS API tools](#direct-maas-api-tools)
  - [The `confirm` safety gate](#the-confirm-safety-gate)
- [Composite workflows](#composite-workflows)
  - [`network_layout` — full topology in one call](#network_layout--full-topology-in-one-call)
  - [`storage_summary` — storage at a glance](#storage_summary--storage-at-a-glance)
  - [`apply_storage_layout` — RAID 1 with `/boot/efi` carved out](#apply_storage_layout--raid-1-with-bootefi-carved-out)
- [Bulk fleet operations](#bulk-fleet-operations)
- [Deployment](#deployment)
- [Development](#development)
  - [Adding or changing a tool](#adding-or-changing-a-tool-against-a-newer-maas)
  - [Tests](#tests)
  - [Layout](#layout)
- [Security notes](#security-notes)
- [License](#license)

---

## Why maasmcp?

MAAS is the de-facto bare-metal provisioning system for Linux fleets. It has a comprehensive REST API — hundreds of endpoints across machines, networks, storage, fabrics, VLANs, subnets, users, etc. — but the raw surface has rough edges for an LLM:

- **Path/query/body parameter shapes vary per resource** (`/machines/?hostname=X` vs `POST /machines/` with multipart form fields).
- **Identifier drift**: internal MAAS ids (VLANs, fabrics) vs IEEE 802.1Q VIDs vs system_ids vs hostnames. The agent has to know which one each call wants.
- **Pagination is universal but client-side invisible** — list endpoints return paginated slices by default and an LLM rarely thinks to walk them.
- **Destructive writes don't confirm.** One slip of a `delete_*` or `release_machine` call can wipe a fleet.

`maasmcp` solves these by:

- **Hand-writing** every tool with Pydantic-typed parameters and `Field(description=…)` docs taken from MAAS's own API documentation (vendored in `docs/reference/maasapi.md`), so the LLM sees the same description a human would.
- **Curating** high-level verbs that handle the messy parts — VLAN-vs-VID translation, auto-pagination, hostname-to-system_id resolution, partial-failure aggregation on bulk ops.
- **Gating** every destructive write behind a `confirm: bool = False` default. Calling `delete_block_device(system_id, id)` without `confirm=True` raises `ValueError` *before* any MAAS call. Use `get_block_device` to verify the target first.

---

## Architecture

```
                 ┌────────────────────────────────────────┐
                 │      MAAS region controller            │
                 │        /api/2.0/ (REST API)            │
                 └─────────────────┬──────────────────────┘
                                   ▲
                                   │ async httpx + OAuth
        ┌──────────────────────────┴───────────────────────┐
        │   src/maasmcp/maas/                              │
        │   ├── client.py       (async httpx + OAuth)      │
        │   ├── errors.py       (typed exception hierarchy)│
        │   ├── paginated_get.py (auto-paginate helper)    │
        │   ├── binding.py      (hide client param from    │
        │   │                    published tool schemas)   │
        │   └── singleton.py    (shared client at runtime) │
        └──────────────────────┬───────────────────────────┘
                               │
                               ▼
              ┌────────────────────────────────────┐
              │   src/maasmcp/curated/             │
              │   126 hand-written tools           │
              │   (one small class per file)       │
              └─────────────────┬──────────────────┘
                                ▼
              ┌─────────────────────────────┐
              │  src/maasmcp/registry.py    │
              │  MCPServer wiring + rebind  │
              └─────────────────────────────┘
                                ▼
              ┌─────────────────────────────┐
              │  Starlette + uvicorn        │
              │  /healthz   (no auth)       │
              │  /mcp       (bearer auth)   │
              └─────────────────────────────┘
                           ▲
                           │   streamable-HTTP
                           │
                  ┌────────┴────────┐
                  │   MCP client    │
                  │  (Claude Code,  │
                  │   Cursor, …)    │
                  └─────────────────┘
```

Two key design properties:

- **Everything is hand-written.** One standard per tool: a small class (`name`, `description`, `run`) in its own module under `src/maasmcp/curated/`, registered and enriched via `curated/_common.py::register_curated`. The server is deterministic and installable without a live MAAS.
- **Dependency direction is one-way.** Tools depend on the shared MAAS client (`maas/client.py`); high-level workflow verbs additionally compose direct tools or raw calls.

---

## Quickstart

### Install

```bash
pip install maasmcp
```

Or from a checkout:

```bash
pip install -e ".[dev]"
```

### Run

The server needs three settings: the MAAS base URL, a MAAS API key (to talk to MAAS), and a bearer token (to gate `/mcp` so random agents can't drive your fleet). Environment variable names use the `MAASMCP_` prefix with `__` as the section delimiter:

```bash
export MAASMCP_MAAS__BASE_URL="https://maas.example.com/MAAS"
export MAASMCP_MAAS__API_KEY="<your-maas-api-key>"
export MAASMCP_SERVER__BEARER_TOKEN="<choose-a-strong-random-token>"
maasmcp serve
```

By default it listens on `0.0.0.0:8765`. Override with `MAASMCP_SERVER__HOST` and `MAASMCP_SERVER__PORT`.

Point your MCP client at `http://localhost:8765/mcp` and authenticate with the bearer token. Liveness check is at `GET /healthz` (no auth):

```bash
curl http://localhost:8765/healthz
# → healthy
```

Readiness probe: `GET /readyz` checks the MAAS upstream and returns 503 when MAAS is unreachable. It requires the bearer token (only `/healthz` is unauthenticated) — pass `-H "Authorization: Bearer $TOKEN"` from your probe config.

maasmcp speaks streamable-HTTP only (no stdio transport). For Claude Code:

```bash
claude mcp add --transport http maas http://localhost:8765/mcp \
  --header "Authorization: Bearer <your-bearer-token>"
```

For Claude Desktop or other stdio-only clients, bridge through an stdio↔HTTP proxy such as `mcp-proxy`.

---

## Configuration

Settings come from a YAML config file **or** `MAASMCP_*` environment variables — the two modes are exclusive (when `--config` is given, the environment only fills `${VAR}` placeholders inside the YAML; there is no per-key env override of file values). Secrets use `${VAR}` indirection so they never sit in committed config:

```yaml
# config.yaml
maas:
  base_url: https://maas.example.com/MAAS
  api_key: ${MAAS_API_KEY}
server:
  bearer_token: ${MAASMCP_BEARER_TOKEN}
  host: 0.0.0.0
  port: 8765
  log_level: info
```

```bash
maasmcp serve --config config.yaml
```

The relevant settings:

| Setting                                                  | Default        | Purpose                                          |
| -------------------------------------------------------- | -------------- | ------------------------------------------------ |
| `maas.base_url` / `MAASMCP_MAAS__BASE_URL`               | *(required)*   | MAAS base URL                                    |
| `maas.api_key` / `MAASMCP_MAAS__API_KEY`                 | *(required)*   | MAAS API OAuth key                               |
| `server.bearer_token` / `MAASMCP_SERVER__BEARER_TOKEN`   | *(required)*   | Bearer token gating `/mcp`; `/healthz` is exempt |
| `server.host` / `MAASMCP_SERVER__HOST`                   | `0.0.0.0`      | Bind address                                     |
| `server.port` / `MAASMCP_SERVER__PORT`                   | `8765`         | HTTP port                                        |
| `server.log_level` / `MAASMCP_SERVER__LOG_LEVEL`         | `info`         | uvicorn / structlog level                        |
| `server.max_paginated_items` / `MAASMCP_SERVER__MAX_PAGINATED_ITEMS` | `1000` | Hard cap on auto-paginated list results          |

The API key and bearer token are read by the runtime, never logged. The observability layer logs bearer tokens only as a 6-char correlation prefix.

---

## Tools

All tools that target a machine accept either `system_id` or `hostname` (exactly one); `hostname` is resolved server-side. (Exceptions: `get_machine` takes a combined `identifier`; `acquire_machine` filters by `hostname` rather than addressing; `machines_power_parameters` takes `id`; `machine_update`'s `hostname` field sets the new name.)

### High-level workflow verbs

These are the opinionated verbs for the jobs you actually do. The tool surface registers **126 hand-written tools** organised by domain, of which the workflow verbs compose others or raw MAAS calls — the plumbing is invisible to the agent.

#### Reads (no gate)

`find_available_machines`, `list_machines`, `get_machine`, `power_status`, `wait_for_state`, `summary`, `network_layout`, `storage_summary`, `list_block_devices`, `get_block_device`, `list_partitions`, `get_partition`, `list_raids`, `get_raid`, `list_volume_groups`, `get_volume_group`, `list_fabrics`, `get_fabric`, `list_spaces`, `get_space`, `list_vlans`, `get_vlan`, `list_subnets`, `get_subnet`, `list_ip_ranges`, `get_ip_range`, `list_interfaces`, `get_interface`.

#### Machine lifecycle (gated writes)

`acquire_machine` (allocating a machine removes it from the shared pool, so it is gated too), `release_machine`, `deploy_machine`, `power_control`.

#### Single-host tag ops (gated)

`tag_machine`, `untag_machine`.

#### Bulk fleet operations (gated, partial-failure aware)

`bulk_release_machines`, `bulk_tag_machines`, `bulk_untag_machines`, `bulk_power_control_machines`.

#### Storage writes (gated, `confirm=True`)

`create_block_device`, `update_block_device`, `delete_block_device`, `set_boot_disk`, `clear_boot_disk` *(gap-closure — surfaces MAAS's missing clear/unset verb as a structured `status: "unsupported"` response with `available_workarounds`; never issues a fake write call)*, `format_block_device`, `mount_block_device`, `create_partition`, `delete_partition`, `format_partition`, `mount_partition`, `unmount_partition`, `create_raid`, `update_raid`, `delete_raid`, `create_volume_group`, `update_volume_group`, `delete_volume_group`, `create_logical_volume`, `delete_logical_volume`.

#### Networking writes (gated, `confirm=True`)

`create_fabric`, `update_fabric`, `delete_fabric`, `create_space`, `update_space`, `delete_space`, `create_vlan`, `update_vlan`, `delete_vlan`, `create_subnet`, `update_subnet`, `delete_subnet`, `create_ip_range`, `update_ip_range`, `delete_ip_range`, `create_interface`, `update_interface`, `delete_interface`, `assign_vlan_to_interface`, `create_bond`, `create_bridge`, `create_interface_vlan`, `link_subnet`, `unlink_subnet`.

#### Composite writes (v0.6.0, gated, `confirm=True`)

`apply_storage_layout`.

### Direct MAAS API tools

Beyond the workflow verbs, maasmcp exposes **33 hand-written direct tools** mapping 1:1 to MAAS REST operations (same names the MAAS API uses) for anything the workflow layer does not cover:

- **Machine ops:** `machine_abort`, `machine_commission`, `machine_delete`, `machine_details`, `machine_lock`, `machine_unlock`, `machine_mark_broken`, `machine_mark_fixed`, `machine_power_parameters`, `machine_update`, `machines_accept`, `machines_create`, `machines_is_registered`, `machines_list_allocated`, `machines_power_parameters`, `machines_read`, `machines_set_zone`
- **Collection reads:** `fabrics_read`, `spaces_read`, `subnets_read`, `vlans_read`, `ipranges_read`
- **Tags:** `tag_delete`, `tag_read`, `tag_update`, `tags_create`, `tags_list`, `tags_read`
- **Users:** `user_delete`, `user_read`, `users_create`, `users_list`, `users_read`

List endpoints auto-paginate up to `max_paginated_items` (default 1000). Collection read tools (`*_read`, `*_list`) accept `paginate=False` to fetch exactly one MAAS-server-sized page instead.

### Discovering tools

With 126 tools, browsing `tools/list` can be overwhelming. Use the `tools_index` helper to get a grouped catalog:

```python
tools_index()
# → {
#     "groups": {
#       "machines": [
#         {"name": "list_machines", "title": "List Machines",
#          "description": "List machines in MAAS.", "read_only": true,
#          "destructive": false, "idempotent": true},
#         ...
#       ],
#       "storage": [...],
#       "network": [...],
#       "tags": [...],
#       "users": [...],
#       "zones": [...],
#       "fleet": [...],
#       "system": [...],
#       "meta": [
#         {"name": "tools_index", "title": "Tools Index", ...}
#       ]
#     }
#   }
```

Every tool description also begins with a `[domain]` tag (for example, `[storage] Create a block device...`) and exposes MCP `ToolAnnotations`:

- `title` — human-friendly Title Case name.
- `readOnlyHint` — `true` for reads, lists, and composite reads.
- `destructiveHint` — `true` for all state-mutating writes (every tool that is not read-only).
- `idempotentHint` — `true` for read-only calls.

These hints let an MCP client filter or sort the tool list without parsing free-text descriptions.

### The `confirm` safety gate

Every destructive verb accepts `confirm: bool = False` and **raises `ValueError` before any MAAS call** when `confirm` is missing or `False`. The default exists for one reason: if an LLM calls the tool without thinking, nothing happens. To actually execute the operation, the agent must re-invoke with `confirm=True` — ideally after using a read verb to verify the target.

```text
agent → delete_block_device(system_id="abc", block_device_id=42)
maasmcp → ValueError: delete_block_device requires confirm=True
agent → get_block_device(system_id="abc", block_device_id=42)
maasmcp → {name: "sdc", size: 500107862016, …}
agent → delete_block_device(system_id="abc", block_device_id=42, confirm=True)
maasmcp → {status: "ok", operation: "delete"}
```

Networking writes are cluster-wide — a typo'd VLAN or subnet can affect every machine on a fabric. They use the same gate but have no business-rule pre-flight checks; the agent is responsible for using `get_vlan` / `get_subnet` / `get_fabric` to verify the target first.

---

## Composite workflows

The three composite tools are the most distinctive features of `maasmcp`. They exist because the equivalent MAAS calls would require a half-dozen round-trips and careful sequencing that an LLM reliably gets wrong.

### `network_layout` — full topology in one call

Returns the machine's interface → VLAN → subnet → fabric tree, plus link-state classification that flags LACP member-suppression as the expected pattern (not a fault). Replaces 5–10 sequential reads with one.

```python
network_layout(system_id="eec43g")
# → {
#     "system_id": "eec43g",
#     "hostname": "living-ewe",
#     "interfaces": [
#       { "name": "eno1", "vlan": 79, "subnet": "10.0.79.0/24", "fabric": "fabric-0",
#         "link_state_classification": "bond_up_members_down" },  # ← expected for LACP
#       { "name": "bond0", "vlan": 79, "subnet": "10.0.79.0/24",
#         "members": [42, 43], "link_state_classification": "bond_up_members_down" },
#     ],
#     "errors": []
#   }
```

On Stage 1 failure it returns `partial=True` plus `errors`; the agent decides whether to retry.

### `storage_summary` — storage at a glance

Counts of block devices, partitions, total size in GiB, plus RAID, volume group, and logical volume counts — fetched in two stages (sequential `list_block_devices`, then a fat gather of per-device partitions + raids + VGs in parallel).

```python
storage_summary(system_id="eec43g")
# → {
#     "block_device_count": 2, "partition_count": 4, "total_size_gib": 1788.5,
#     "raid_devices": 1, "volume_groups": 0, "logical_volumes": 0
#   }
```

### `apply_storage_layout` — RAID 1 with `/boot/efi` carved out

The classic RAID-with-ESP layout is a sequence of dependent operations: carve partitions, format the ESP, format the data partitions, build the RAID, format the RAID, mount everything, and tell MAAS which disk is the boot disk. Forget one step or get the order wrong and the system won't boot.

`apply_storage_layout` takes a single dict spec and sequences `create_partition`, `format_partition`, `mount_partition`, `create_raid`, and `set_boot_disk` for you, in the right order. Three layout types are supported:

- `raid_with_esp` — partitions carved on each member disk, ESP (`fat32` mounted at `/boot/efi`) on raw disks, RAID over the remaining partitions, rootfs on RAID. Use this for **RAID 1 with `/boot/efi` off-array**.
- `raid` — partitions carved on each member disk, RAID over all of them. No ESP (BIOS boot only).
- `plain` — no RAID, one or more disks partitioned and optionally formatted + mounted.

```python
apply_storage_layout(
    system_id="eec43g",
    layout={
        "layout_type": "raid_with_esp",
        "disks": [
            {"block_device_id": 1, "partitions": [
                {"size": "1G", "fstype": "fat32", "mount_point": "/boot/efi"},
                {"size": "remaining"},
            ]},
            {"block_device_id": 2, "partitions": [
                {"size": "1G", "fstype": "fat32"},   # mirror copy of the ESP, no mount
                {"size": "remaining"},
            ]},
        ],
        "raid": {"level": 1, "name": "md0", "filesystem": "ext4", "mount_point": "/"},
        "boot_disk": {"block_device_id": 1},
    },
    confirm=True,
)
```

Returns `{status: "complete" | "partial", completed_steps, failed_step, errors, rollback_hint}`. On `partial` there is **no automatic rollback** — the agent decides whether to retry, restore via MAAS's raw `op-restore_storage_configuration` endpoint (not a curated verb), or live with the partial state.

Requires MAAS cluster setting `default_storage_layout=blank` so MAAS does not re-layout storage on commission/deploy. If your MAAS uses a different default, this layout will not survive to deploy.

#### Manual recipe (driving leaf verbs directly)

For incremental workflows where you want full control:

```text
with MAAS cluster setting default_storage_layout=blank:
  create_partition × N        # one per disk, sized to fit ESP + rootfs
  format_partition × N        # ESP and rootfs partitions
  mount_partition × N         # /boot/efi and /boot on the appropriate ones
  create_raid(level=1, partitions=[...])
  format_block_device(raid_id, fstype)
  mount_block_device(raid_id, "/")
  set_boot_disk(block_device_id=...)
  deploy_machine(system_id, distro="ubuntu/noble")
```

---

## Bulk fleet operations

The four bulk verbs fan out across many machines and aggregate results so partial failures are visible without raising:

- `bulk_release_machines(system_ids, erase=True, comment=…)` — uses MAAS's batch endpoint, returns per-host status.
- `bulk_tag_machines(system_ids, tag)` — `asyncio.gather` with a `Semaphore(10)` cap.
- `bulk_untag_machines(system_ids, tag)` — same shape.
- `bulk_power_control_machines(system_ids, action)` — `action ∈ {on, off, cycle}`; per-host errors reported as `upstream <status>`.

```python
bulk_power_control_machines(system_ids=["eec43g", "8smce7"], action="cycle")
# → [{"system_id": "eec43g", "status": "ok"},
#    {"system_id": "8smce7", "status": "error", "error": "upstream 504"}]
```

Inspect every entry — bulk verbs never raise on partial failure, so an agent that doesn't iterate the result list will silently leave failing hosts in their pre-call state.

---

## Deployment

A `Dockerfile` is included. The MAAS URL, API key, and bearer token drive the whole process (nested `MAASMCP_` names, same as `docker-compose.yml`):

```bash
export MAASMCP_MAAS__BASE_URL="https://maas.example.com/MAAS"
export MAASMCP_MAAS__API_KEY="<your-maas-api-key>"
export MAASMCP_SERVER__BEARER_TOKEN="<choose-a-strong-random-token>"  # required, no default
```

Build and run:

```bash
docker build -t maasmcp:0.10.1 .
docker run --rm -p 8765:8765 \
  -e MAASMCP_MAAS__BASE_URL -e MAASMCP_MAAS__API_KEY -e MAASMCP_SERVER__BEARER_TOKEN \
  maasmcp:0.10.1
```

A compose file (`docker-compose.yml`) is included and uses the same variable names. Note: compose substitutes an unset `${VAR}` as an **empty string** — the server rejects an empty bearer token at startup, so a missing `MAASMCP_SERVER__BEARER_TOKEN` fails closed rather than running unauthenticated.

Health probe (no auth, useful for k8s liveness/readiness):

```bash
curl -fsS http://localhost:8765/healthz
```

---

## Development

### Adding or changing a tool against a newer MAAS

All tools are hand-written. To support a newer MAAS API version, consult the vendored spec (`docs/reference/maasapi.md`) or a live `/api/2.0/describe/`, then add or update the tool class under `src/maasmcp/curated/`, register it in `curated/_common.py`, and make sure `src/maasmcp/curated/_catalog.py` maps its name to the right domain and annotations. Document the change in `CHANGELOG.md`, bump the package version, run the full suite, then cut a release tag.

### Tests

```bash
pytest                 # unit + integration (702 passed, 3 env-gated skips)
pytest -m e2e --no-cov # end-to-end against a live MAAS (gated; --no-cov: the
                       # coverage floor is sized for the full suite)
ruff check src tests
ruff format --check .
mypy --strict src
```

- **Unit tests** cover every tool, the MAAS client, config, and auth.
- **Integration tests** boot the Starlette app under `uvicorn` and drive MCP `initialize`/`tools/list`/`tools/call` over streamable-HTTP, verifying the bearer middleware.
- **E2E tests** (`pytest -m e2e`) assert against a real MAAS instance. Off by default (env-gated skips): set `MAASMCP_E2E_MAAS_URL` + `MAASMCP_E2E_SYSTEM_ID` (bulk/storage flows) and `MAASMCP_E2E_URL` + `MAASMCP_E2E_KEY` (acquire/release flow). Nothing runs them automatically — they're for manual pre-release verification.

### Layout

```text
src/maasmcp/
├── cli.py                  # typer: serve
├── config.py               # pydantic-settings + ${VAR} expansion
├── server.py               # Starlette app factory + uvicorn entry
├── registry.py             # MCPServer instance + tool registration
├── auth.py                 # bearer-token middleware (healthz exempt)
├── observability.py        # structlog config + sanitizers
├── maas/                   # async httpx client, errors, pagination, rebind
└── curated/                # 126 hand-written tools
    ├── _common.py          # registration + shared helpers
    └── …                   # one file per tool

tests/
├── unit/                   # all 126 tools, MAAS client, config, auth, registry pin
├── integration/            # HTTP transport handshake under uvicorn
├── fixtures/maas/          # response fixtures
└── e2e/                    # live MAAS, gated by marker
```

The full design rationale lives at `docs/specs/2026-07-07-maasmcp-design.md`. Implementation plans for each release are at `docs/plans/2026-07-07-*.md`. The vendored copy of the MAAS API v2 documentation (the authoritative reference for endpoint semantics) is at `docs/reference/maasapi.md`.

---

## Security notes

- **Two credentials live in this process**: `MAASMCP_MAAS__API_KEY` (used to call MAAS) and `MAASMCP_SERVER__BEARER_TOKEN` (used to gate `/mcp`). Neither is ever logged in full. Bearer tokens appear in logs only as a 6-char correlation prefix. The bearer token must be non-empty (empty is rejected at startup and by the middleware) — an empty token would otherwise authenticate headerless requests.
- **`machine_power_parameters` / `machines_power_parameters` expose BMC/IPMI credentials** — MAAS's `power_parameters` op returns the BMC username/password for IPMI-type machines. Anyone holding the MCP bearer token can read them; treat the bearer token accordingly.
- **The `confirm` gate is your last line of defence.** Destructive and state-mutating verbs (including machine allocation and tagging, which change fleet state) raise before any MAAS call when `confirm=True` is missing. Treat the gate as the contract — never weaken it.
- **Bulk verbs return per-host status**, never raise on partial failure. An agent that doesn't iterate the result list will silently leave the failing hosts in their pre-call state. Inspect every entry.
- **`apply_storage_layout` is destructive and irreversible** at the storage layer. Use `storage_summary` and `list_block_devices` first to confirm disk identity.
- **Networking writes are cluster-wide.** A typo'd VLAN deletes more than you intended. Verify with `get_vlan` / `get_subnet` / `get_fabric` before `confirm=True`.
- **LACP bond member suppression is normal.** `link_state_classification: "bond_up_members_down"` is the expected pattern for healthy LACP — the slave interfaces are suppressed by the kernel. Only `"bond_down_members_down"` indicates a real physical-layer fault.

---

## License

Apache-2.0. See `LICENSE`.
