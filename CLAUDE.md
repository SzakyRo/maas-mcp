# maasmcp

MCP server exposing Canonical MAAS bare-metal provisioning to LLM agents.
Package name: `maasmcp` (version 0.10.1), Python ≥ 3.11, Apache-2.0.

## Common commands

All commands assume the project root and use `uv` (the project ships a
`uv.lock`; do not introduce a `requirements.txt` or `pip-compile`-style
fallback without discussion).

| Task | Command |
|---|---|
| Install dev env | `uv sync --locked --extra dev` |
| Run tests (80% coverage gate) | `uv run pytest` |
| Lint | `uv run ruff check .` |
| Format | `uv run ruff format .` |
| Typecheck (strict, `src/maasmcp` only) | `uv run mypy .` |
| Run MCP server locally (port 8765) | `uv run python -m maasmcp serve` |
| Show CLI help | `uv run maasmcp --help` |

The same `uv sync --locked --no-dev --no-editable` recipe is what the
`Dockerfile` uses — keep them in sync.

## Conventions

- Python source lives in `src/maasmcp/` (flat layout, hatchling
  `packages = ["src/maasmcp"]`). Tests live in `tests/` (`unit/`,
  `integration/`, `e2e/`).
- Tooling config lives in `pyproject.toml` (`[tool.ruff]`,
  `[tool.mypy]`, `[tool.pytest.ini_options]`). No separate
  `setup.cfg`, `mypy.ini`, or `.flake8` file.
- Ruff rules enabled: `E, F, W, I, B, UP, SIM, RUF` (line-length 100,
  target-version py311). `E501` is ignored — let ruff format wrap.
- Test suite enforces `--cov-fail-under=80`. New code must keep
  coverage above the gate.
- E2E tests under `tests/e2e/` are gated by `MAASMCP_E2E_*` env vars
  and skipped otherwise (see `[tool.pytest.ini_options].markers`).
- Wire-format deps are major-pinned (`httpx<1.0`, `mcp<2.2`). Bump
  deliberately — see `pyproject.toml` comments for the blast radius
  of each pin (notably `MCPServer._tool_manager._tools`).

## Repository layout to be aware of

- `src/maasmcp/maas/` — wire-format binding for the MAAS REST API.
- `src/maasmcp/curated/` — curated tool surface exposed via MCP.
- `scripts/42-maas-storage-layout.sh` — project-owned bash helper
  (NOT a CI script; invoked manually when laying out storage on a
  MAAS box).
- `docs/plans/` and `docs/specs/` — this
  project's own planning/spec archive. The `superpowers/` name
  here is a project naming choice and is unrelated to ECC
  superpowers tooling (which lives in `.claude/`).
- `Dockerfile` (Python 3.11-slim, uv 0.8 pinned) and
  `docker-compose.yml` (host network, env-driven config).

## Runtime environment

`maasmcp` reads env vars with the `MAASMCP_` prefix and `__` as
the nested-key separator (see `src/maasmcp/config.py`). Required
for a live run:

- `MAASMCP_MAAS__BASE_URL`
- `MAASMCP_MAAS__API_KEY`
- `MAASMCP_MAAS__VERIFY_TLS` (default `true`)
- `MAASMCP_SERVER__BEARER_TOKEN`
