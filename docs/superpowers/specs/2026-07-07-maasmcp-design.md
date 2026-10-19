# maasmcp — Design Spec

**Date:** 2026-07-07
**Status:** Approved design (awaiting user review of this written spec)
**Owner:** Unassigned
**MAAS API target:** Canonical MAAS 3.x (pin during implementation)

> **Repo state note:** this project directory was empty at the start of
> brainstorming and is not yet a git repository. The implementation plan will
> include `git init` as its first step so that the committed `_generated/`
> subtree and this spec file are tracked.

---

## 1. Purpose

`maasmcp` is an MCP (Model Context Protocol) server that exposes Canonical MAAS
bare-metal provisioning to LLM agents. It speaks the MCP streamable-HTTP
transport, exposes the full MAAS API surface via auto-generated tools, and ships
a curated set of opinionated verbs that compose those tools into useful
workflows.

Out of scope for v1: per-user audit (MAAS OAuth is single-user for the server),
Prometheus metrics, e2e CI against live MAAS, and LLM-in-the-loop evals.

---

## 2. Architecture

### 2.1 Runtime components

| Component | Role | Lifetime |
|---|---|---|
| HTTP server (Starlette + uvicorn via FastMCP) | Exposes MCP streamable-HTTP transport on configurable port; loads tool registry | Long-lived, one process |
| Auth middleware | Validates `Authorization: Bearer <token>` with `hmac.compare_digest`; exempts `/healthz` | Per-request |
| Tool registry | Loads generated tools + curated overlay into FastMCP at startup | Startup |
| MAAS client (async httpx) | Thin wrapper over MAAS REST; owns API key or OAuth signing; retries 5xx with exponential backoff (250ms / 1s / 4s); translates errors | Long-lived |

### 2.2 Build-time components

| Component | Role | Lifetime |
|---|---|---|
| Describe fetcher | Hits `/api/2.0/describe/` against a configured MAAS; writes a versioned JSON snapshot under `src/maasmcp/_generated/describe_snapshot.json` | One-shot, run by maintainers |
| Tool generator | Reads the snapshot, emits one Python file per MAAS operation under `src/maasmcp/_generated/tools/`, plus a `registry.py` | One-shot, run by maintainers |

### 2.3 Dependency direction

```
MAAS describe snapshot  ──►  generated tools  ──►  curated verbs
                                       ▲                  ▲
                                       │                  │
                                  MAAS client ◄───────────┘
```

The MAAS client is shared by both layers. Curated verbs depend on the MAAS
client directly (not on the generated tools) when a raw call is simpler, and on
the generated tools when they want to reuse an existing tool's validation.

Generated code is **committed**, not generated at runtime. This makes the server
deterministic, installable without a MAAS instance handy, and easy to vendor.

---

## 3. Generated tool layer

### 3.1 Source of truth

MAAS publishes its API as a JSON document at `<base_url>/api/2.0/describe/`.
The shape (top level):

```
{
  "resources": [
    {
      "name": "machines",
      "description": "...",
      "operations": {
        "list":   { "method": "GET",  "path": "machines/", "parameters": {...} },
        "create": { "method": "POST", "path": "machines/", "parameters": {...} },
        "update": { "method": "PUT",  "path": "machines/{system_id}/", "parameters": {...} },
        ...
      }
    },
    ...
  ]
}
```

### 3.2 Generation rules

1. **One MCP tool per MAAS operation.** Tool name = `{resource}_{operation}`
   (e.g. `machines_list`, `machines_create`, `machines_update`).
2. **Pydantic v2 input model per operation.** Path parameters are split out
   (required, positional); query/body parameters become a Pydantic model.
3. **MAAS type system → Python:** string/int/bool/array/object translate
   directly; `$ref` resolves to a referenced model; `oneOf` / `anyOf` becomes
   discriminated unions or `Optional`.
4. **Each parameter carries `Field(description=...)`** from MAAS's own
   parameter docs — the LLM uses these.
5. **Output schema** is a Pydantic model when MAAS describe pins a type;
   otherwise `dict` or `list[dict]`.
6. **Path-param binding** is automatic via a generated `url_for(**path_params)`
   helper per operation.
7. **Pagination.** Every list operation is wrapped to auto-paginate
   `?limit=N&offset=M` up to `max_paginated_items` (default 1000,
   configurable). A `paginate: bool = False` opt-out exists per call; when set,
   the tool returns exactly one page (the MAAS server's default page size)
   and ignores `max_paginated_items`.
8. **Tool metadata.** Names, descriptions, and input schemas are introspectable
   by the LLM via the MCP standard `tools/list` request.
9. **Generated code is committed.** The `_generated/` subtree is in version
   control.
10. **Versioning.** Snapshot JSON is keyed by MAAS API version. Re-running
    the generator against a newer MAAS produces a new `_generated/` subtree
    in a dedicated PR; the package version bumps; CHANGELOG notes which MAAS
    API version is supported.

### 3.3 What the generator does NOT do

- It does not invent input validation beyond MAAS's own schema.
- It does not translate error messages — MAAS responses are surfaced verbatim
  to the LLM in `isError=true` tool results.

---

## 4. Curated overlay

Twelve hand-written, opinionated verbs. Each composes one or more generated
tools and adds the validation / parameter curation that MAAS's raw API forces
on callers. Names use bare verb-y forms so they're discoverable; generated
tools use `{resource}_{operation}` so they're distinguishable in
introspection.

| Verb | Purpose | Composes |
|---|---|---|
| `acquire_machine(constraints)` | Find idle machine matching constraints; allocate; return system_id + power state. **Non-idempotent** — what MAAS gives you. | `machines_list`, `machines_allocate` |
| `find_available_machines(constraints)` | Read-only sibling of `acquire_machine` | `machines_list` |
| `deploy_machine(system_id, distro, user_data=None, hwe_kernel=None)` | Set OS config, commission if needed (commissioned when the machine's `status` is `NEW` or `READY` but its commissioning flag is unset), deploy, wait for completion | `machines_update`, polled `machines_read` |
| `release_machine(system_id, comment=None, erase=True)` | Deallocate and erase. **`erase=True` is the aggressive default** — to prevent silent state leakage between tenants | `machines_release`, optional disk erase |
| `power_status(system_id)` | Read current power state | `machines_read` |
| `power_control(system_id, action)` | `on` / `off` / `cycle`; validates safe transitions (won't power-off a deploying machine) | `machines_power_*` |
| `wait_for_state(system_id, target_states, timeout)` | Generic polling helper | `machines_read` |
| `list_machines(filter)` | Typed filter (status, pool, tag, zone, hostname_glob) | `machines_list` |
| `get_machine(system_id_or_hostname)` | Accepts either identifier; returns normalized view | `machines_list` + lookup |
| `tag_machine(hostname, tag)` | Add a tag | `machines_add_tag` |
| `untag_machine(hostname, tag)` | Remove a tag | `machines_remove_tag` |
| `summary()` | Counts by status, pool, zone; totals across fleet | `machines_list`, `pods_list` |

### 4.1 What the overlay deliberately does NOT include

- Raw MAAS CRUD wrappers — those live in the generated layer.
- Commissioning script authoring — too domain-specific, generated layer only.
- Network / fabric editing — too easy to break deployments, generated layer
  only.
- User / permission management — security-sensitive, out of scope for v1.

---

## 5. HTTP transport, auth, configuration

### 5.1 Server

- FastMCP streamable-HTTP transport, mounted in a Starlette app, served by
  uvicorn.
- Console script: `maasmcp serve --config /etc/maasmcp/config.yaml`.
- Binds `0.0.0.0:$MAASMCP_PORT` (default `8765`), single asyncio loop.
- `/healthz` mounted alongside MCP routes, exempt from auth (for LB / monitor).

### 5.2 Auth — client to server

- Static bearer token in `Authorization: Bearer <token>` header.
- Configured via `MAASMCP_BEARER_TOKEN` env var or `server.bearer_token` in YAML.
- Compared with `hmac.compare_digest` on every request.
- Binary valid / invalid; no scopes, no per-user identity, no rotation.

### 5.3 Auth — server to MAAS

Two modes, selected by config:

- **`api_key`** (default): one MAAS API key from `MAAS_API_KEY` env var.
- **`oauth`**: MAAS OAuth1 with consumer key / secret / token / token-secret,
  signed per request.

The MAAS client validates the chosen mode on startup; refuses to start if
creds are missing.

### 5.4 Configuration schema

```yaml
maas:
  base_url: https://maas.example.com/MAAS
  api_key: ${MAAS_API_KEY}        # or oauth consumer_key/secret/token/token_secret
  api_version: "2.0"
  verify_tls: true

server:
  host: 0.0.0.0
  port: 8765
  bearer_token: ${MAASMCP_BEARER_TOKEN}
  log_level: info
  request_timeout_seconds: 60
  max_paginated_items: 1000

generated:
  catalog_refresh_on_start: false
```

Loaded with Pydantic Settings; `MAASMCP_*` env vars override any file value.
Validation errors fail fast with a readable message. YAML uses `${VAR}`
indirection so secrets never sit in committed files.

### 5.5 Logging & observability

- `structlog` JSON output to stdout.
- Per MCP request: client IP, bearer-token prefix (first 6 chars, never the
  full token), tool name, latency, outcome.
- Per MAAS upstream call: method, path (with path params replaced by
  `{name}`), status, latency.
- No request bodies, no full tokens in logs.
- Prometheus `/metrics` endpoint is **out of scope for v1**. Logging hooks are
  written so it can be added without refactoring.

### 5.6 Error handling at the boundary

| Failure | Response |
|---|---|
| Bearer token missing / wrong | `401 Unauthorized`, no body that leaks why |
| MAAS upstream 4xx | Pass through MAAS error JSON in `isError=true` tool result |
| MAAS upstream 5xx | Retry up to 3 times with exponential backoff (250ms / 1s / 4s); on final failure, surface `MCPUpstreamError` with last status + URL |
| Network timeout | Same retry policy; on final failure, surface `MCPUpstreamTimeout` |

---

## 6. Testing strategy

Six layers, cheapest first. Optional layers are gated.

| # | Layer | Scope | Speed |
|---|---|---|---|
| 1 | Generator unit tests | Feed pinned describe snapshot fixture; snapshot-test the generator's output (the `_generated/` subtree) | Fast, deterministic |
| 2 | Generated layer unit tests | Parameter coercion, pagination caps, error translation, path-param substitution — spot-checked on one resource per major MAAS object, plus a property test that **every registered tool is callable** and matches its Pydantic input model | Fast |
| 3 | MAAS client tests | Success path, 4xx pass-through, 5xx retry-then-fail, network timeout, OAuth signature (validated against a known-good MAAS doc vector) — via `respx` against committed response fixtures | Fast |
| 4 | Curated overlay tests | One test per curated verb (12 tests). Mocks MAAS client at the boundary; asserts right generated tools were composed in right order with right args; asserts the verb's own validation (e.g. `release_machine(erase=True)` issues the erase call) | Fast |
| 5 | Auth + HTTP transport tests | Bearer present → 200; missing / malformed / wrong → 401 (no leak); `/healthz` 200, no auth; streamable-HTTP transport works end-to-end via in-process MCP SDK helpers | Medium |
| 6 | End-to-end against real MAAS | Separate `tests/e2e/`, **skipped by default**. Runs only when `MAASMCP_E2E_URL` and `MAASMCP_E2E_KEY` are set (CI-provisioned MAAS). `pytest -m e2e` marker | Slow, gated |

### 6.1 Coverage targets

| Component | Threshold | Notes |
|---|---|---|
| Curated overlay | ≥85% | Enforced. Where bugs hurt. |
| MAAS client | ≥80% | Enforced. |
| Generator | ≥80% | Enforced. |
| Generated layer | **Exempt** | Auto-generated code excluded so the threshold isn't gamed by generated lines |

### 6.2 Fixtures

- MAAS describe snapshots per supported MAAS version under
  `tests/fixtures/maas/describe/`.
- Recorded response fixtures under `tests/fixtures/maas/responses/`, keyed by
  tool name.
- Both committed and refreshed by an admin command:
  `python -m maasmcp refresh-fixtures --against <maas_url>`. Never runs in CI
  automatically.

### 6.3 What we deliberately do NOT test in v1

- LLM-in-the-loop scenarios.
- Load / soak tests.
- Fuzz testing of the generator input.
- Property-based tests of the Pydantic schemas.

---

## 7. Repo layout, packaging, release

### 7.1 Repo layout

```
maasmcp/
├── pyproject.toml
├── README.md
├── LICENSE                       # Apache-2.0
├── CHANGELOG.md
├── docs/
│   └── superpowers/
│       └── specs/
│           └── 2026-07-07-maasmcp-design.md
├── src/
│   └── maasmcp/
│       ├── __init__.py
│       ├── __main__.py           # python -m maasmcp
│       ├── cli.py                # typer CLI
│       ├── config.py             # pydantic-settings
│       ├── server.py             # Starlette app factory + uvicorn entry
│       ├── auth.py               # bearer-token middleware
│       ├── maas/
│       │   ├── __init__.py
│       │   ├── client.py         # async httpx wrapper, retry + OAuth
│       │   ├── errors.py         # typed exception hierarchy
│       │   └── pagination.py     # iterator + cap helpers
│       ├── _generated/           # committed, regenerated by `maasmcp generate`
│       │   ├── describe_snapshot.json
│       │   ├── registry.py
│       │   └── tools/
│       │       └── ...           # one file per operation
│       └── curated/              # 12 hand-written verbs
│           └── ...
├── tests/
│   ├── conftest.py
│   ├── unit/
│   │   ├── test_generator.py
│   │   ├── test_generated_layer.py
│   │   ├── test_maas_client.py
│   │   ├── test_curated.py
│   │   └── test_auth.py
│   ├── integration/
│   │   └── test_http_transport.py
│   ├── fixtures/
│   │   └── maas/
│   │       ├── describe/
│   │       └── responses/
│   └── e2e/                      # skipped by default
│       └── test_acquire_release.py
└── .github/
    └── workflows/
        ├── ci.yml                # lint + unit + integration on every PR
        └── release.yml           # build + publish to PyPI on tag
```

### 7.2 Package metadata

- Name: `maasmcp`
- Console script: `maasmcp` → `maasmcp.cli:main`
- Python: `>=3.11`
- Runtime deps: `httpx`, `mcp[cli]`, `pydantic>=2.5`, `pydantic-settings`,
  `structlog`, `starlette`, `uvicorn[standard]`, `typer`, `PyYAML`
- Dev deps: `pytest`, `pytest-asyncio`, `pytest-cov`, `respx`, `ruff`,
  `mypy`, `hatchling`

### 7.3 Release flow

- Versioning: PEP 440, start at `0.1.0`.
- MAAS API version support is encoded as a runtime config flag
  (`maas.api_version`), not as install extras — simplifies dependencies.
- Tags: `vX.Y.Z` on `main` trigger `.github/workflows/release.yml`.
- CI: ruff + mypy + pytest on every PR; integration tests on `main`;
  publish to PyPI on tag (via trusted publishing, no long-lived tokens).
- PRs that regenerate against a new MAAS version follow the convention:
  title `chore(regen): MAAS 3.X.Y → 3.Y.Z`, description links to MAAS release
  notes, diff reviewed with `?w=1`.

### 7.4 Deprecation policy

When MAAS retires an endpoint, `/api/2.0/describe/` returns a `deprecated:
true` field on the operation. The generator honors this by:

1. Emitting the tool with `@deprecated` and a `DeprecationWarning` on import.
2. Including the deprecation notice in the tool's MCP description string so
   the LLM is warned at tool-selection time.
3. Logging a `WARNING` on server startup listing every deprecated tool that's
   still registered.
4. Keeping the tool in the registry for one minor release, then dropping it.
   The CHANGELOG entry for the dropping release lists the removed tools.

---

## 8. Open questions for implementation planning

These do not block the spec but should be resolved during the writing-plans
phase:

1. **OAuth signature details** — confirm exact MAAS OAuth1 signature scheme
   against the official Python example before implementing.
2. **MAAS 3.x → 4.x drift** — what is our policy if `/api/2.0/describe/`
   changes shape materially?
3. **`summary()` return shape** — confirm we want a single flat dict, not a
   nested resource→counts dict.

---

## 9. Glossary

- **MCP** — Model Context Protocol. The standard LLM-tool transport from
  Anthropic.
- **MAAS** — Canonical Metal-as-a-Service. Bare-metal provisioning.
- **Curated verb** — A hand-written MCP tool that composes one or more
  generated tools.
- **Generated tool** — An MCP tool emitted by the build-time generator, one
  per MAAS operation.
- **`/api/2.0/describe/`** — MAAS's self-describing API endpoint, consumed by
  the generator.
