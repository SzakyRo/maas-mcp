# AGENTS.md

Project-specific instructions for AI coding agents working in this
repository. Tool-agnostic — readable by Claude Code, Codex, Cursor,
OpenCode, Gemini, and other harnesses that respect the `AGENTS.md`
convention.

For Claude Code specifically, see `CLAUDE.md` (which carries the same
content with Claude-Code-specific framing). The two files are kept in
sync intentionally.

## Project summary

`maasmcp` — MCP server exposing Canonical MAAS bare-metal
provisioning to LLM agents. Python ≥ 3.11, Apache-2.0, package
`maasmcp` at `src/maasmcp/`.

## Build / test / lint / typecheck / dev

The project uses `uv` (a `uv.lock` is checked in). Do not introduce a
`requirements.txt` or `pip-compile` fallback.

| Task | Command |
|---|---|
| Install dev env | `uv sync --locked --extra dev` |
| Run tests (80% coverage gate) | `uv run pytest` |
| Lint | `uv run ruff check .` |
| Format | `uv run ruff format .` |
| Typecheck (strict, `src/maasmcp`) | `uv run mypy .` |
| Run MCP server locally (port 8765) | `uv run python -m maasmcp serve` |
| Show CLI help | `uv run maasmcp --help` |

## Conventions

- Python source at `src/maasmcp/`, tests at `tests/` (`unit/`,
  `integration/`, `e2e/`). Tooling config in `pyproject.toml` — no
  separate `setup.cfg`, `mypy.ini`, `.flake8`.
- Ruff rules: `E, F, W, I, B, UP, SIM, RUF`, line-length 100,
  target-version py311. `E501` ignored (let `ruff format` wrap).
- Tests must keep `--cov-fail-under=80` green.
- E2E tests under `tests/e2e/` are gated by `MAASMCP_E2E_*` env vars
  and skipped otherwise (see `[tool.pytest.ini_options].markers`).
- Wire-format deps are major-pinned (`httpx<1.0`, `mcp<2.2`). Bump
  deliberately — see `pyproject.toml` comments for the blast radius
  of each pin (notably `MCPServer._tool_manager._tools`).
- Prefer immutable data flow inside request handlers (see
  `.claude/rules/ecc/python/patterns.md`).
- Read `.claude/rules/ecc/python/security.md` before touching auth,
  bearer-token handling, or Pydantic `ValidationError` rendering.

## Runtime env vars

`MAASMCP_` prefix, `__` as nested-key separator (see
`src/maasmcp/config.py`):

- `MAASMCP_MAAS__BASE_URL`
- `MAASMCP_MAAS__API_KEY`
- `MAASMCP_MAAS__VERIFY_TLS` (default `true`)
- `MAASMCP_SERVER__BEARER_TOKEN`

## Things to know

- The `docs/superpowers/` directory is the project's own plans/specs
  archive (markdown, dated 2026-07-* and 2026-09-*). Unrelated to
  ECC superpowers tooling in `.claude/`.
- `scripts/42-maas-storage-layout.sh` is project-owned and is invoked
  manually on MAAS hosts; it is not a CI script.
- The `Dockerfile` (Python 3.11-slim, uv 0.8 pinned) and
  `docker-compose.yml` (host network, env-driven) are the canonical
  way to run the server in a container.
