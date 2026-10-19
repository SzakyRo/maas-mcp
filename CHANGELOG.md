# Changelog

All notable changes to maasmcp are documented here.

## [Unreleased]

### Changed (breaking for MCP clients)
- Unified VLAN parameter convention: `vid` always means the IEEE 802.1Q
  VLAN ID. `get_vlan`/`update_vlan`/`delete_vlan` renamed `vlan_id` → `vid`;
  `assign_vlan_to_interface`, `create_bond`, `create_bridge`,
  `create_interface_vlan`, and `update_interface` renamed `vlan` → `vid`.
  `create_subnet`/`update_subnet` are unchanged: `vlan` remains the MAAS
  internal VLAN id, `vid` the 802.1Q VID — matching MAAS's own wire layout
  (all VLAN endpoints are keyed by vid per maasapi.md).
- `storage_summary`'s `total_size_gb` field is renamed `total_size_gib`:
  the value was always computed with a 1024³ divisor (GiB); the name now
  matches the math.
- `bearer_token` now requires at least 1 character at config load: an empty
  expected token previously authenticated headerless requests
  (hmac.compare_digest matched "no header" against ""). Short tokens remain
  allowed — entropy is the operator's call on trusted networks.

### Fixed
- `deploy_machine` now fails fast on real MAAS failure states
  ("Failed commissioning" / "Failed deployment") instead of waiting for a
  nonexistent "Failed" status and timing out silently for 30 minutes.
- Non-timeout transport failures (DNS, connection refused, TLS errors) are
  no longer misreported as "upstream timed out": the client raises
  `MCPUpstreamError(status_code=0)` with the original exception chained,
  and request logs record the true exception class instead of "<timeout>".
  Log entries now also report the true retry decision per attempt.
- Empty-dict POST/PUT bodies are normalized to no body at the client layer;
  tools like `machine_lock`/`machine_abort`/both unmount verbs called
  without a comment no longer send the empty multipart that MAAS rejects
  with 400.
- `update_raid` and `update_volume_group` fail fast with a clear error when
  called with nothing to change, instead of PUT-ing an empty body.
- `get_machine` validates its `identifier` with the same id rules as every
  other machine tool (was interpolated raw into the MAAS URL path) and its
  `os` field no longer reports a stray leading space.
- `tag_machine`/`untag_machine` resolve hostnames BEFORE the confirm gate
  like every other tool, so a typo'd hostname reports "no such machine"
  instead of "pass confirm=True".
- Auth middleware fails closed on websocket/unknown scope types and rejects
  requests carrying more than one `Authorization` header (RFC 7235);
  `/readyz` uses a dedicated 10s probe timeout instead of the 5-minute
  tool-call budget; logs go to stderr (stdio-transport safe); the request
  log extracts tool names from JSON-RPC batch payloads and still logs
  clients that disconnect mid-upload.
- The tool rebind (`maas/binding.py`) now fails loudly at startup if MCP
  SDK internals (`_tool_manager._tools`) shift, instead of silently serving
  126 broken tools; `mcp` is pinned to the 2.1.x line accordingly.

### Packaging / CI
- Release workflow verifies the git tag matches `pyproject.toml` version
  before publishing, runs ruff+mypy, and pins the `build` package.
- Dockerfile base images are pinned by digest; `.dockerignore` excludes
  `.venv/`/`dist/`; compose publishes port 8765 and has a `/healthz`
  healthcheck.

### Changed (metadata)
- `clear_boot_disk` is now annotated destructive in the tool catalog even
  though it only issues a GET — the annotation matches operator intent
  (it asks MAAS to forget the boot-disk pin, which is a mutating concept).

### Fixed
- Deterministic upstream 500s no longer burn the full retry schedule.
  MAAS surfaces Django ORM DoesNotExist lookups (e.g. "PartitionTable
  matching query does not exist" on table-less disks) as bare 500s; those
  can never succeed on retry, so the client now fails fast on that phrase
  and lets downstream fallbacks (like `list_partitions`' inline fallback)
  run immediately instead of after ~5.25s of pointless backoff.
- Tool errors now lead with MAAS's own reason instead of the bare status
  code. A partition that does not fit used to surface as
  `Error executing tool create_partition: upstream 400`; it now reads
  `size: Partition cannot be saved; not enough free space on the block
  device. (upstream 400)`. The status only qualifies the detail and is
  omitted for synthetic failures (status_code=0), so no bogus
  "upstream 0" appears. Wire/log format otherwise unchanged.
- `list_partitions` no longer errors on block devices with no partition
  table (fresh unused disks, raw whole-disk RAID members). MAAS returns an
  undocumented 500 ("PartitionTable matching query does not exist") for
  those — the tool now catches that specific failure and falls back to the
  block device's inline `partitions` list, which MAAS serves reliably
  (empty for table-less disks). Unrelated 500s still propagate.

### Added
- All 65 machine-addressed tools now accept `hostname` in addition to `system_id`
  (provide exactly one; both set must agree). Bulk ops and `machines_accept` take
  a `hostnames` list resolved with a single fleet fetch. `machines_set_zone`
  (`nodes`), `tag_machine`, and `untag_machine` join the shared resolver.
  Backwards compatible: `system_id` merely became optional.

## [0.10.1] — 2026-08-31

### Fixed
- `get_machine` resolves non-hex system_ids (MAAS system_ids are base-36 —
  e.g. '84t4pa' contains 't','p'). Previously such identifiers were
  misclassified as hostnames and errored when no hostname matched; now a
  hostname miss falls through to a direct system_id GET. (Found during live
  busy-feline re-provisioning with v0.10.0.)

## [0.10.0] — 2026-08-31

Full audit of all tools against the vendored MAAS API v2 documentation
(`maasapi.md`), with ambiguous points cross-checked against upstream MAAS
source. Fixes behavioral bugs, closes doc'd-parameter gaps, and hardens
agent-facing descriptions.

### Added
- Zone CRUD tools: `zones_list`, `zones_create`, `zone_read`, `zone_update`,
  `zone_delete` (zones are name-addressed in MAAS).
- `unmount_block_device` (`op-unmount` on whole devices — mirrors
  `unmount_partition`; the path helper existed unused).
- Params: `update_vlan` gains `mtu`/`dhcp_on`/`primary_rack`/`secondary_rack`/
  `relay_vlan`/`space`; `create_vlan` gains `mtu`/`space`; `create_subnet` and
  `update_subnet` gain `cidr` (update), `vid`, `rdns_mode`, `allow_dns`,
  `allow_proxy`, `active_discovery`, `managed`, `disabled_boot_architectures`;
  `delete_subnet` gains `force`; `machine_delete` gains `force` (`?force=1`);
  `machines_read` gains the server-side `status` filter; `release_machine` and
  `bulk_release_machines` gain a real `force`; `power_control` gains
  `stop_mode` (soft/hard) and `comment`; `create_bond` gains the full tuning
  set (lacp_rate, miimon, up/downdelay, xmit hash policy, num_grat_arp, mtu,
  accept_ra, mac_address, tags); `create_logical_volume` keeps size-optional
  with corrected examples; `format_partition`/`format_block_device` gain
  `label`; `link_subnet` gains `force`; `update_interface` gains `mtu` and
  `accept_ra`; `update_block_device` gains `size` (LV resize), `block_size`,
  `uuid`; `tag_update` gains `new_name`; `machines_accept` takes a list of
  system_ids (repeated multipart parts, as MAAS documents);
  `machines_create.mac_addresses` takes a list.

### Fixed
- `bulk_power_control_machines` action `cycle` no longer POSTs the
  nonexistent `op-power_cycle`; it synthesizes off + pause + on per host,
  like single-machine `power_control`.
- `bulk_release_machines` sends the system_id list as repeated `machines`
  parts (was a JSON-stringified blob that MAAS would 400) and now fans out
  per-machine `op-release` calls so `erase`/`secure_erase`/`quick_erase`/
  `force` are actually honored — the collection op-release only accepts
  `machines` + `comment`.
- `deploy_machine` base64-encodes `user_data` before sending (MAAS expects
  base64; raw cloud-init text previously landed undecodable).
- `create_interface` posts to `op-create_physical` with `mac_address`
  required (was a bare collection POST MAAS doesn't define, with name/mac
  requiredness flipped).
- `create_bridge` sends the singular `parent` field per the doc (bridges
  take one parent; `parents` is bond-only); >1 members now raise client-side
  with guidance to create a bond first.
- VLAN tools (`get_vlan`/`update_vlan`/`delete_vlan`) now accept vid 0 —
  the fabric's untagged default VLAN, required for enabling MAAS-managed
  DHCP. `create_vlan` still enforces 1..4094.
- `get_space` accepts space_id 0 (the built-in 'undefined' space).
- `create_partition` drops the silent no-op params `fstype` and
  `partition_table_type` (upstream ignores them), makes `size` optional
  (omit = all available space, per doc), and adds `uuid`.
- `apply_storage_layout` maps partition `size: "remaining"` to the size-less
  POST MAAS expects (the literal sentinel 400s upstream), and a RAID
  `filesystem` is now formatted and mounted on the RAID's virtual md device
  (previously formatted the filesystem-group id and never mounted).
- `create_subnet`/`update_subnet` send `dns_servers` as one comma-separated
  string (doc contract), not repeated form parts.
- `update_space` requires `name` (MAAS marks it required even when only
  changing the description).
- `update_fabric`/`update_space`/`update_subnet`/`update_vlan`/
  `update_ip_range` now raise on a non-dict response instead of returning a
  fabricated `{}`.
- `get_machine` falls back to the `?hostname=` lookup when a hex-looking
  identifier 404s as a system_id (all-hex hostnames like `decaf0` no longer
  fail).
- `vlans_read` takes `fabric_id: int` and builds the path via the shared
  helper (was str + inline f-string).

### Improved (agent-facing descriptions)
- Hidden side effects disclosed: `create_bond` pre-marks members as
  10G/connected; `create_interface_vlan` rewrites the parent's untagged
  VLAN; `network_layout`'s `vlan`/`linked_subnet` fields are documented as
  heuristics; `power_status` documented as a cached read; `machine_details`
  documented as BSON/text hardware dumps (not the machine record);
  `users_create` carries the doc's plaintext-password warning;
  `machines_set_zone` tells agents `nodes` is a system_id;
  `storage_summary` documents best-effort partition counting (raid-member
  500s); `machine_abort` says what it actually aborts.
- `tags_list`/`tags_read` and `users_list`/`users_read` now say they are
  intentional aliases and which to prefer.



### Added — IP address lifecycle tools (from live provisioning)

Upstream gap found while provisioning bare metal through the server: when a
static link is unlinked from an interface, MAAS keeps the reserved
`IPAddress` row, and relinking then 404s "IP address is already in use".
Previously the only remedy was a raw authenticated POST outside the MCP —
now the whole lifecycle is first-class:

- **`ip_addresses_read`** — `GET /ipaddresses/` with `ip` / `all` / `owner`
  filters and the standard `paginate` flag. Note for agents: MAAS's default
  listing only shows *your own* user reservations; pass `all=True` (admin)
  to find reservations owned by others.
- **`ip_address_reserve`** — `op=reserve` with `subnet` (CIDR) or `ip`
  (one required), plus optional `hostname`/`mac`. Confirm-gated.
- **`ip_address_release`** — `op=release` with `ip`, plus admin `force`
  (other-owner rows) and `discovered` (valid only with `force`, enforced
  locally). Confirm-gated; returns nothing on 204.

Also corrected the `ip_addresses_read` assumption from 0.8.2's notes: an
empty default listing is MAAS's documented user-scope behavior, not a bug.

## [0.8.2] — 2026-08-30

Live-fire fixes from provisioning real hardware through the server
(full RAID/partition/VLAN build of a bare-metal node via the MCP tools).

### Fixed — verified against live MAAS

- **`unlink_subnet` now sends the link id.** MAAS's unlink op documents a
  single body param `id` — the subnet *link's* id (from an interface's
  `links[].id`), not the subnet id. Current releases 400
  `{"id": ["This field is required."]}` on the old `subnet=` body. New
  preferred param `link_id`; legacy `subnet_id` remains as a fallback for
  older releases. At least one is required; if both are given, `link_id`
  wins. Validation errors fire before any HTTP call.
- **`format_partition` / `format_block_device` reject `fstype="raid"` up
  front** with an actionable message. Verified live: MAAS 400s the format
  op for raid — membership is established by `create_raid` attaching raw
  members (the raid filesystem marker is automatic on join and removed on
  delete). The opaque upstream 400 is now a local `ValueError` pointing at
  create_raid, and no HTTP request is made.
- `create_raid`'s schema description now states that raw/unformatted
  members are fine (prevents agents from attempting the raid-format
  dead-end).

## [0.8.1] — 2026-08-30

### Fixed — live-MAAS compatibility

- **Collection pagination is now version-tolerant.** Verified against a
  live MAAS (3.x at 10.72.91.100): `/machines/` (and several other
  collections) reject `?limit=`/`?offset=` outright — the constraint
  validator answers 400 `{"limit": ["No such constraint."], ...}`, while
  `/pods/` on the same deployment paginates fine. `paginate_get` now falls
  back to a single unpaginated GET when the *first* page request fails
  with 400; a mid-walk 400 still propagates, and a 400 caused by the
  caller's own filters surfaces unchanged from the retry. This fixes
  `summary`, `list_machines`, `acquire_machine`, `find_available_machines`,
  `tags_list`, and `users_list` (all broken against unpaginated MAAS
  releases since 0.7.1's pagination change). One extra harmless round trip
  per list call on such deployments; no behaviour change on paginating
  releases.

## [0.8.0] — 2026-08-30

Migrate from MCP SDK 1.x to **`mcp` SDK 2.1.1** (`>=2.1,<3.0`). The SDK's
v1 `mcp.server.fastmcp.FastMCP` became `mcp.server.mcpserver.MCPServer`
in v2; the tool-registration API (`add_tool`, the `Tool` record shape,
`func_metadata`) is unchanged, so the port is import-path-mechanical for
all 116 curated tools.

### Behaviour changes

- The rebind wrapper now translates tool-side `ValueError` into the SDK's
  `ToolError`. v1 surfaced validation messages (e.g. the confirm gate's
  "confirm=True required") in the tool-error content verbatim; v2 hides
  the message of unexpected exceptions ("Error executing tool X"), which
  would have made every confirm-gate rejection useless to agents. The
  translation preserves the v1 agent-visible contract exactly.
- Streamable HTTP now rejects request bodies over 4 MiB with HTTP 413
  (SDK v2 `max_request_body_size` default — identical to maasmcp's own
  request-log buffer cap). The 2026-07-28 spec revision's self-describing
  POSTs are supported; `initialize` is still honoured for session setup.
- `streamable_http_app()` is per-call fresh in v2 (no shared cached
  session manager), so the test-suite session-manager reset fixture was
  retired.

### Notes

- `json_response=True` moved from the server constructor to
  `streamable_http_app()` — plain-JSON responses remain the transport
  default for maasmcp.
- In-process tests now use v2's `Client(server)` instead of the removed
  `mcp.shared.memory.create_connected_server_and_client_session`;
  `CallToolResult.is_error` replaced `isError`.

## [0.7.2] — 2026-08-30

Second review round (fix-regression trace of 0.7.1, deeper security pass,
published-schema audit, test-quality pass, docs/ops verification).

### Security

- **Tag names and usernames are now percent-encoded before URL path
  interpolation** (`quote_segment`, applied to tag_machine, untag_machine,
  bulk_tag_machines, bulk_untag_machines, tag_read, tag_update, tag_delete,
  user_read, user_delete). A crafted tag like `x/../../machines/abc/?op=delete`
  previously normalized into a real machine-delete POST — a semantic bypass
  of the confirm gate.
- Non-ASCII `Authorization` headers now get a clean 401 instead of crashing
  the middleware (`hmac.compare_digest` rejects non-ASCII str).
- `bearer_prefix` never prints a short token in full (`<short>` below
  8 chars); `sanitize_path` now actually collapses id-like path segments
  (six-char alnum system ids and integers → `{id}`) and is no longer a no-op.
- Bulk fleet tools cap `system_ids` at 500 entries (bounds per-call upstream
  fan-out).
- The MAAS three-part API key auto-split now requires all three parts to be
  alphanumeric (colon-bearing opaque Bearer keys are no longer silently
  reinterpreted as OAuth triples) and logs an INFO when splitting.
- Upstream-timeout error URLs drop the query string (parity with 4xx/5xx).
- The multipart builder rejects CR/LF in field names (values remain
  protected by the per-request random boundary — documented in code).

### Behaviour changes

- **Fabric id 0 is now valid** in every fabric-scoped tool (`fabric-0` is
  MAAS's real default fabric); other resource ids still require ≥ 1.
- `link_subnet`: `DHCP` added to the mode enum; `AUTO` description corrected
  (MAAS assigns an IP from the subnet at deploy time — not DHCP); `STATIC`
  without `ip_address` now auto-selects (previous raise contradicted the
  MAAS spec).
- `create_bond` / `create_bridge`: the `vlan` param now takes the IEEE 802.1Q
  **VID** and translates it internally like the rest of the interface
  family (was: raw passthrough with ambiguous naming); `bond_mode` is
  optional (MAAS default: active-backup).
- `release_machine` gains `secure_erase` / `quick_erase` (parity with
  `bulk_release_machines`) and no longer claims full-overwrite erase is
  "secure".
- Pagination: the oversized-page guard now detects duplicate pages by
  content — endpoints honoring `offset` but ignoring `limit` are walked
  correctly instead of truncating after page 1; endpoints ignoring both
  still stop after one echo.
- Non-idempotent calls no longer pay a pointless backoff sleep before
  raising, and log `retrying=False` accurately.
- `machines_power_parameters` / `machine_power_parameters` describe the
  actual response (power parameters, incl. BMC credentials) — not "machine
  object".
- Config: `.env` in the working directory is now read for the env-only load
  mode; `maasmcp serve` reports a missing `${VAR}` placeholder as a clean
  configuration error (no traceback).
- `__version__` is read from package metadata (was a hardcoded stale
  "0.6.0").

### Docs / tests

- README: the broken `claude_desktop_config.json` stdio example was removed
  (maasmcp is streamable-HTTP only — use `claude mcp add --transport http`
  or an mcp-proxy bridge); `/readyz` bearer requirement documented;
  `pytest -m e2e --no-cov` (the coverage floor is sized for the full suite);
  `mount_block_device` added to the tool listing; the false "CI runs e2e
  nightly" claim removed; `maasapi.md` described accurately.
- Request-log overflow regression test rewritten to script the ASGI receive
  channel (Starlette's TestClient coalesces bodies, so the previous test
  never exercised the overflow path).
- `wait_for_state` re-pinned as a read in the registry test, and the
  READS/WRITES split is now enforced programmatically against the published
  schemas.
- New end-to-end `tools/call` integration tests prove the rebind layer
  (client injection at call time) and confirm-gate rejection work over the
  MCP protocol, not just at the tool level.
- Env-gated e2e suites updated to the gated tool contracts
  (`confirm=True`, Title-case `Ready`, client-side status filtering, entered
  async client context).
- Wire-level pagination tests cover multi-page `acquire_machine` /
  `list_machines`; pagination offset progression pinned; retry tests no
  longer sleep ~5s of real backoff.

## [0.7.1] — 2026-08-30

Post-review hardening of the 0.7.0 all-hand-written surface (follow-up to a
five-lens code review: security, correctness, consistency, tests,
maintainability).

### Security

- **An empty `server.bearer_token` no longer disables authentication.**
  `bearer_token` now requires `min_length=1` and the auth middleware rejects
  an empty presented token before comparison — previously
  `hmac.compare_digest("", "")` authenticated any headerless request when the
  token was empty (reachable e.g. via an unset
  `${MAASMCP_SERVER__BEARER_TOKEN}` in docker-compose, which substitutes an
  empty string with only a warning).
- `system_id` (and friends) interpolated into MAAS URL paths are now
  validated against a strict single-segment allowlist
  (`^[A-Za-z0-9._~-]{1,64}$`) in every machine/storage/network tool —
  blocks path-traversal and query-smuggling through path parameters.
- Upstream 4xx/5xx error URLs no longer include the query string (may carry
  user input such as hostnames); matches the existing timeout-path policy.
- A per-request log middleware no longer buffers an unbounded request body:
  past a 4 MiB cap the remainder streams without buffering, so a jumbo
  unauthenticated POST can't be fully resident in memory.
- The client logs a warning at startup when `maas.base_url` is plain HTTP
  (OAuth PLAINTEXT credentials would travel in cleartext).
- `user_delete` URL-encodes `transfer_resources_to` in the path query.

### Behaviour changes (tool contracts)

- **`acquire_machine`, `tag_machine`, `untag_machine`, `bulk_tag_machines`,
  `bulk_untag_machines` are now confirm-gated.** Allocation and tagging are
  fleet state changes; they now match every other mutating tool
  (`confirm=True` required, gate fires before any HTTP call).
- `list_machines` and `acquire_machine` auto-paginate: MAAS's default page
  size previously dropped machines beyond page 1, which could make
  `acquire_machine` report no match (or allocate the wrong machine) on fleets
  larger than one page.
- The misleading `paginate` flag was removed from the six single-object read
  tools (`machine_details`, `machine_power_parameters`,
  `machines_power_parameters`, `machines_is_registered`, `user_read`,
  `tag_read`) — `paginate=True` used to raise on their non-list responses.
- `machines_is_registered` now advertises `bool` in its schema (the endpoint
  returns a JSON boolean).
- Only idempotent methods (GET/HEAD/DELETE) are retried; POST/PUT are
  replayed zero times to avoid duplicate creates after transport failures.

### Fixed

- `/readyz` now actually returns 503 on MAAS upstream failures — it caught
  `httpx.HTTPError`, but `MaasClient` translates upstream failures into
  `MAASError` subclasses, so the probe used to 500 on timeout/connect/5xx.
- `server.max_paginated_items` is no longer ignored: the server passes the
  full config to `MaasClient` instead of a bare `MaasConfig` (which silently
  forced the 1000 default).
- Pagination no longer duplicates items if an endpoint ignores
  `limit`/`offset` (stops on an oversized page instead of re-fetching it),
  and the short-page check compares against the actual requested page size.
- `wait_for_state` raises builtin `TimeoutError` (not `MCPUpstreamTimeout`,
  which falsely signalled a MAAS outage) and uses `get_running_loop()`.
- Malformed JSON from MAAS now raises `MCPUpstreamError` instead of leaking
  raw `json.JSONDecodeError`; 3xx responses are treated as errors (httpx
  does not follow redirects here).
- Removed the dead `generated:` config block (`catalog_refresh_on_start`),
  a codegen leftover that was accepted but did nothing.
- README corrected end-to-end: env var names are the real nested
  `MAASMCP_MAAS__*` / `MAASMCP_SERVER__*` forms, the false "env wins" claim
  removed (file and env modes are exclusive), tool count 112 → 116, missing
  `update_interface`/`link_subnet` added to the listing, ToC anchor fixed,
  architecture diagram and testing section match reality; `machines_read`'s
  description no longer claims `list_machines` doesn't exist.
- CI now builds on `master` (was `main`) and enforces `ruff format --check`
  in addition to `ruff check`.

### Refactored (no behaviour change)

- `network_layout.run` split into stage helpers (`_stage1`,
  `_resolve_touched_vlans`, `_fetch_vlans`, `_fetch_fabric_vlan_counts`,
  `_touched_subnets`, `_join_interfaces`); `apply_storage_layout.run` split
  into `_apply_partitions` / `_apply_raid` / `_apply_boot_disk` behind a
  `_Sequencer` result accumulator. Both composite tools keep their exact
  response shape and partial-failure semantics.
- `register_curated` is now a 3-line loop over a module-level `ALL_TOOLS`
  tuple (was a 141-line function).
- Removed the duplicated `fabric_vlans_path` helper (use `vlans_path`).
- `Dockerfile` installs from `pyproject.toml` only (dropped the
  hand-mirrored dependency list and the redundant `PYTHONPATH`).
- The shared `maas_client` test fixture moved to
  `tests/unit/curated/conftest.py`; the integration test server binds port 0
  instead of probing-then-releasing a free port; assorted stale docstrings
  and test markers corrected.

### Tests

- New rejection tests prove the confirm gate fires before any HTTP call for
  `power_control`, `deploy_machine`, `acquire_machine`, `tag_machine`,
  `untag_machine`, `bulk_tag_machines`, `bulk_untag_machines`.
- The shared `maas_client` fixture is no longer copy-pasted across 46 test
  files; it lives in `tests/unit/curated/conftest.py`.
- Coverage now measures the whole `maasmcp` package (was `curated`+`maas`
  only) with `--cov-fail-under` enforcement.

## [0.7.0] — 2026-08-30

### Changed

- **Codegen layer removed.** The MAAS `/describe/`-driven generator
  (`maasmcp codegen / generate` / `refresh-fixtures` CLI commands,
  `src/maasmcp/codegen/`, `src/maasmcp/_generated/`) is gone. The 33
  previously generated tools are now hand-written curated tools under
  `src/maasmcp/curated/`, following the same class pattern as the rest of
  the surface (`name` / `description` / `run` / `register`). All tool
  names, HTTP verbs, paths, and confirm gates are unchanged — no MCP
  client migration needed. Total surface: 116 hand-written tools.
- The MCP server display name is now `maasmcp` (was `maasmcp-generated`).
- Whole repo is now `ruff format`-checked.

### Fixed

- **`machine_delete`, `tag_delete`, `user_delete` crashed at call time**
  (`TypeError: delete() got an unexpected keyword argument 'params'`).
  The codegen template emitted `params=` on DELETE calls that
  `MaasClient.delete()` never accepted; the hand-written replacements call
  it correctly.
- `confirm=True` is no longer leaked into MAAS request bodies/query
  strings on the ported tools — it is a local confirmation gate only.
- `server.py` annotated the lifespan wrapper with the non-existent
  `Starlette.router.lifespan_context` (latent `NameError` via
  `get_type_hints`); replaced with a proper `Lifespan` callable alias.
- Stale integration assertion for `machines_list` (shadowed by
  `list_machines`) and missing inter-sentence spaces in ten curated tool
  descriptions.

## [0.6.0] — 2026-07-07

### Added
- `apply_storage_layout(system_id, layout, confirm)` — composite verb that
  sequences leaf CRUD (create_partition, format_partition, mount_partition,
  create_raid, set_boot_disk) to build multi-disk storage layouts. Supports
  `raid_with_esp` (RAID 1 with `/boot/efi` off-array), `raid` (RAID without
  ESP), and `plain` (no RAID) layout types. Returns a partial-result dict on
  mid-sequence failure; raises only on caller-error conditions.
- README "Custom storage layout" recipe section showing the exact call
  sequence for RAID 1 with ESP off-array, plus when to use the composite
  vs. driving leaf verbs directly.

### Notes
- Requires MAAS cluster setting `default_storage_layout=blank` so MAAS does
  not re-layout storage on commission/deploy.
- The composite returns `status="partial"` on mid-sequence failure (matching
  v0.5.0 `network_layout` semantics) so the agent can decide whether to
  retry, restore, or live with the partial state.

## [0.5.0] — 2026-07-07

### Added

- **Networking surface (35 new curated verbs)**:
  - Fabric: `list_fabrics`, `get_fabric`, `create_fabric`, `update_fabric`, `delete_fabric`
  - Space: `list_spaces`, `get_space`, `create_space`, `update_space`, `delete_space`
  - VLAN: `list_vlans`, `get_vlan`, `create_vlan`, `update_vlan`, `delete_vlan`
  - Subnet: `list_subnets`, `get_subnet`, `create_subnet`, `update_subnet`, `delete_subnet`
  - IP Range: `list_ip_ranges`, `get_ip_range`, `create_ip_range`, `update_ip_range`, `delete_ip_range`
  - Interface: `list_interfaces`, `get_interface`, `create_interface`, `delete_interface`, `assign_vlan_to_interface`, `create_bond`, `create_bridge`, `create_interface_vlan`, `unlink_subnet`
  - Composite read: `network_layout(system_id)` — single-call interface→VLAN→subnet→fabric tree

- **14 network path helpers** in new `src/maasmcp/curated/_network_paths.py`
- **`_validate_id` helper** added to `_storage_paths.py` — single-id sibling to `_validate_ids` for non-machine-scoped verbs (Fabric, Space, VLAN, Subnet, IP Range)

### Changed

- Curated surface grows 43 → 78 verbs.

### Notes

- Networking writes are cluster-wide destructive (a typo'd VLAN can affect every machine on a fabric); v0.4.0's `confirm: bool = False` gate is the only friction by design. No pre-flight business-rule checks.
- `network_layout` returns `partial=True` plus `errors` if Stage 1 fails; the agent decides whether to retry.
- `link_subnet` (op-link_subnet) is deferred to v0.6.0 — MAAS auto-links subnets via VLAN assignment, which is sufficient for the bond→VLAN→subnet workflow.

## [0.4.0] — 2026-07-07

### Added

- 5 RAID verbs: `list_raids`, `get_raid`, `create_raid`, `update_raid`, `delete_raid`
- 5 volume-group verbs: `list_volume_groups`, `get_volume_group`, `create_volume_group`, `update_volume_group`, `delete_volume_group`
- 2 logical-volume verbs (write-only): `create_logical_volume`, `delete_logical_volume`
- 6 new path helpers in `_storage_paths.py`: `raids_path`, `raid_path`, `volume_groups_path`, `volume_group_path`, `lv_create_path`, `lv_delete_path`
- `storage_summary` gains real `raid_devices`, `volume_groups`, and `logical_volumes` counts (replacing v0.3.0 `0/0` placeholders)
- Sequential Stage 1 / fat Stage 2 fetch shape in `storage_summary` — one extra gather entry adds raids + VGs without an extra round-trip

### Security

- M2 schema-drift raise extended to `get_raid`, `get_volume_group`, `create_raid`, `create_volume_group`

## [0.3.1] — 2026-07-07

### Changed (polish)
- All 15 storage verbs now validate `system_id` and path IDs through a
  single `_validate_ids` helper colocated with `_storage_paths.py`.
  Refactor preserves exact `ValueError` message wording; no behavior
  change visible to agents.
- `get_block_device` and `get_partition` now raise `ValueError` (with
  substring "non-dict") when MAAS returns a non-dict response body at
  status 200, instead of silently returning `{}`. Surfaces schema drift
  loudly.

### Added (test symmetry)
- `test_empty_system_id_raises_value_error` on `test_list_partitions.py`
  and `test_get_partition.py` (M3).
- `test_block_device_id_zero_raises_value_error` on `test_get_partition.py`
  (M4).
- `test_empty_system_id_with_confirm_true_still_fails` replicated across
  the 9 destructive verbs that didn't already have it (M6): update,
  delete, set_boot_disk, format (block device); create, delete, format,
  mount, unmount (partition).
- `test_get_block_device_non_dict_response_raises` and
  `test_get_partition_non_dict_response_raises` (M2).

## [0.3.0] — 2026-07-07

### Added
- 5 read verbs: `list_block_devices`, `get_block_device`, `list_partitions`,
  `get_partition`, `storage_summary` (two-stage fetch, RAID/VG counts as
  placeholders for v0.4.0).
- 10 destructive verbs behind `confirm: bool = False` gate:
  `create_block_device`, `update_block_device`, `delete_block_device`,
  `set_boot_disk`, `format_block_device`, `create_partition`,
  `delete_partition`, `format_partition`, `mount_partition`,
  `unmount_partition`.
- `_storage_paths.py`: shared path templating for storage endpoints
  (single source of truth, prevents drift across 10 verbs).

### Changed
- Curated layer grows from 16 → 31 verbs. Storage verbs are destructive;
  agents must pass `confirm=True` to execute them.

## [0.2.0] — 2026-07-07

### Added
- `bulk_release_machines` — release N machines in one MAAS batch POST (uses `/api/2.0/machines/op-release` with the `machines` list field). Returns per-system_id status; never raises on partial failure.
- `bulk_tag_machines` / `bulk_untag_machines` — add or remove a tag from N machines in parallel via `asyncio.gather` (MAAS has no batch tag endpoint). Concurrency capped at 10. Per-system_id status.
- `bulk_power_control_machines` — power on/off/cycle N machines in parallel via per-id `/machines/{id}/op-power_*`. Concurrency capped at 10. Per-system_id status.
- `list_machines` accepts three new optional kwargs: `zone` (server-side filter via MAAS `zone` query param), `cpu_count_min` (server-side, mapped to MAAS `cpu_count` query param), `memory_min` (server-side, mapped to MAAS `mem` query param (string)). Backwards compatible: existing callers pass nothing and see the same result.

### Changed
- Surface is additive but agent-friendliness is the headline — bulk verbs expose partial failure without raising so an agent can decide what to retry.

## [0.1.1] — 2026-07-07

### Fixed
- MCP endpoint was reachable only at `/mcp/mcp` because the inner
  `streamable_http_app()` was mounted under `Mount("/mcp", ...)` while the
  SDK already routes at `/mcp` internally. Mount now uses `Mount("/", ...)`
  so the public URL matches the README's documented `http://localhost:8765/mcp`.
- Forward the inner MCP app's `lifespan_context` to the outer Starlette
  so `StreamableHTTPSessionManager.run()` actually starts on startup
  (without this, every request 500s with "Task group is not initialized").

### Added
- Integration test that drives the full streamable-HTTP transport under
  uvicorn on a random port and asserts (a) `/healthz` exempt from auth,
  (b) `/mcp` without bearer → 401, (c) `/mcp` with bearer → 200 with
  `text/event-stream` content-type and an `mcp-session-id` header —
  proving lifespan startup, bearer auth, and MCP server processing all
  work over real HTTP. A second test guards the `/mcp` mount path
  against the double-prefix regression. A third test covers the wire
  protocol (tools/list returns generated + curated tools) via the
  in-memory transport.

## [0.1.0] — 2026-07-07

### Added
- Initial release.
- Streamable-HTTP MCP transport with bearer-token auth.
- Auto-generated tool layer from MAAS `/api/2.0/describe/` (pinned to MAAS 3.5).
- 12 curated verbs: `acquire_machine`, `find_available_machines`, `deploy_machine`,
  `release_machine` (default `erase=True`), `power_status`, `power_control`,
  `wait_for_state`, `list_machines`, `get_machine`, `tag_machine`, `untag_machine`,
  `summary`.
- MAAS client supports `api_key` and `oauth` auth modes.
- 5xx + network-timeout retry policy: 3 attempts at 250ms / 1s / 4s.
- Six-layer test strategy with curated overlay ≥85% coverage.
