# 2026-07-09 — Fix MAAS MCP deploy/wait timeout layering

## Why

During vocal-collie provisioning (release → ready cycle) the user observed that
`deploy_machine` and `wait_for_state` returned `operation timed out` after
~25–30 minutes of wall-clock even though the underlying MAAS polling
succeeded — the machine actually reached `Deployed` shortly after our timeout
fired. We worked around it with raw httpx polling via
`docker exec … python -c "asyncio.run(...)"` against `MaasClient` inside the
container, which is a violation of `mcp-only-rule`. The fix is to either
lengthen the relevant timeouts or give `wait_for_state` a resumable shape so
transport-layer disconnects don't lose polling progress.

## Empirical evidence from this session

- `deploy_machine(timeout_seconds=3600)` returned "timed out" at ~30 min while
  vocal-collie was still in `Rebooting`; subsequent `list_machines` showed
  it had reached `Deployed` minutes earlier.
- `wait_for_state(target_states=[Ready,Failed], timeout_seconds=2400)` returned
  "timed out" twice during release-then-ready cycle on both machines; polling
  in a separate channel (Docker exec → MaasClient.get) showed the machines did
  reach Ready.
- `release_machine` (default `erase=true`) on a 4×SSD machine (2×240GB +
  2×1.92TB) goes through phases: `Deployed → Disk erasing → Released →
  Commissioning → Ready`. The 1.92TB SSDs make the erase step dominate
  wall-clock time; ~25 min is realistic.
- Successful releases ended at "Released" with `power_state=off`; MAAS then
  auto-PXEs and re-commissions to `Ready` without explicit user action.

## Three timeout layers (all must be sized correctly)

| Layer | Code location | Current default | What it caps |
|---|---|---|---|
| Tool `timeout_seconds` | `curated/deploy_machine.py:39` (`1800`), `curated/wait_for_state.py:27` (`600`) | OK when overridden per-call | Wall-clock budget for the *internal polling loop* |
| Per-call httpx timeout | `cfg.server.request_timeout_seconds` → `MaasClient(..., timeout_seconds=...)` (`server.py:59`, `config.py:129`, `client.py:93`) | **60 s** | Every individual MAAS HTTP request |
| MCP streamable HTTP transport session | set by `FastMCP.streamable_http_app` + `StreamableHTTPSessionManager` (likely in `server.py:create_app` and Starlette mounts) | ~30 min (whatever the SDK defaults to) | **The session lifetime — disconnects the long-poll call regardless of tool-level timeouts** |

Layer 3 is the real culprit. Layers 1 and 2 are configured correctly in our
calls; layer 3 fires first because the MCP transport itself has a session
timeout we never explicitly raised.

## Recommended fixes (4 items, scope-graded)

### Item 1 — Raise `request_timeout_seconds` default (cheap, low risk)
File: `src/maasmcp/config.py:129`
Change `default=60` → `default=300`. Lets each MAAS API call take up to 5 min
instead of 1 — covers slow BMC probes under load.

### Item 2 — Raise MCP transport session timeout (real fix for the symptom)
File: `src/maasmcp/server.py` (`create_app`, around the `streamable_http_app`
mount and any `StreamableHTTPSessionManager` config).
Trace the SDK defaults, override to 3600 s (1 h) or 7200 s (2 h). Likely
either a Starlette `TimeoutMiddleware` configuration or a kwarg passed to
`StreamableHTTPSessionManager`. If the SDK doesn't expose a knob, the
fallback is to switch to `stateless=True` mode and accept that each poll
cycle is a separate session.

### Item 3 — Resumable `poll_status` tool (architectural long-term fix)
Add a new curated tool that continues polling from a previous `wait_for_state`
call. Spec:
- `wait_for_state` returns immediately with a `poll_token` (UUID) if the
  target state isn't reached within ~25 min (configurable; `transport_safe_seconds`)
- New `poll_status(system_id, poll_token, target_states)` resumes polling
  using the same poll interval
- Token expires after `transport_safe_seconds` × 4 to prevent zombie polls
- Caller pattern: tool-loop with `poll_status` until target reached or the
  user signals stop

This makes long MAAS deploys a first-class supported pattern instead of
falling out of the curated surface to raw httpx.

### Item 4 — Document transport-vs-tool timeout behavior
Files: `src/maasmcp/curated/deploy_machine.py:description` (line 30),
`src/maasmcp/curated/wait_for_state.py:description` (line 19).
Add one sentence to each tool's `description`:
> "If a transport-layer timeout fires before this tool's timeout, re-call to
> resume from the current MAAS state."

## Scope options for implementation

### Minimal (items 1 + 4) — 5 min, no architectural risk
- `config.py:129` default 60 → 300
- Two doc-string additions
- User knows what to expect; the symptom we hit is not fixed (transport layer
  still disconnects), but the doc sets expectations correctly.

### Standard (items 1 + 2 + 4) — fixes the symptom, requires SDK internals trace
- All of Minimal
- Trace and raise the MCP transport session timeout in `server.py`
- May require switching to stateless mode if SDK doesn't expose a knob

### Comprehensive (all 4) — long-term best fit
- All of Standard
- New `poll_status` tool with `poll_token` lifecycle
- Deprecates the raw-httpx-poll-via-docker-exec workaround completely
- Aligns with [[mcp-only-rule]] because long operations stay in the curated surface

## Cross-references
- [[mcp-only-rule]] — the underlying reason to fix this
- [[maasmcp-storage-requires-ready]] — companion finding from same session
- [[maasmcp-multi-raid-storage]] — companion finding from same session

## Status

Awaiting user decision on which scope (Minimal / Standard / Comprehensive)
to implement. Pre-existing work in this session is complete; this is the
follow-up cleanup item the user surfaced at the end.
