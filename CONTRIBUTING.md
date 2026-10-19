# Contributing to `maasmcp`

Thanks for contributing. This guide covers the workflow, conventions,
and quality gates that PRs need to clear. For project context, see
`README.md` and the design specs under `docs/superpowers/specs/`.

## Quick start

1. Clone the repo.
2. Install dev dependencies: `uv sync --locked --extra dev`.
3. Run the test suite: `uv run pytest` (must pass with
   `--cov-fail-under=80` green).
4. Lint and typecheck: `uv run ruff check . && uv run mypy .`.

The project uses Python 3.11+ (matches the Dockerfile).

## Pre-PR gate

Run all four locally before opening a PR:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run pytest
```

All four must be clean. CI will fail otherwise.

## Workflow

- Branch from `main`.
- Keep commits focused; one logical change per commit. Imperative
  mood in the subject (`Fix NTP regression in bulk-machine-ops`,
  not `Fixed …`).
- Reference the relevant plan/spec in
  `docs/superpowers/specs/<topic>.md` if one exists for the area
  you're changing. Plans live alongside specs under
  `docs/superpowers/plans/`.

## Code style

- Ruff enforces `E, F, W, I, B, UP, SIM, RUF` (line-length 100,
  py311). `E501` is intentionally ignored — let `ruff format` wrap
  long lines.
- mypy runs in **strict** mode over `src/maasmcp/`. Add type
  annotations for any new public surface.
- `TypedDict` / `NotRequired` come from `typing_extensions`, not
  the stdlib `typing` module — pydantic on Python 3.11 rejects the
  stdlib forms (see `pyproject.toml`).
- Prefer immutable data flow inside request handlers. The codebase
  generally rebuilds rather than mutates; if you're tempted to
  mutate a request object mid-flight, ask first.

## Tests

- Tests live in `tests/` (`unit/`, `integration/`, `e2e/`). Unit
  tests use `respx` to mock httpx calls into the MAAS REST API.
- New code must keep `--cov-fail-under=80` green. If you add a code
  path, add a unit test that covers it.
- Markers: `e2e` (skipped unless `MAASMCP_E2E_*` env vars are set),
  strict markers enforced via `--strict-markers`.
- The `asyncio_mode = "auto"` setting means async test functions
  don't need an explicit `@pytest.mark.asyncio` decorator.

## Wire-format dependency pins

The project deliberately pins some wire-format deps by major version:

- `httpx<1.0` — 1.x rewrites transport internals; the curated
  client assumes the 0.x shape.
- `mcp<2.2` — `src/maasmcp/maas/binding.py`'s rebind depends on the
  double-private `MCPServer._tool_manager._tools` attribute; a
  minor bump could rename it. `rebind_all` fails loudly if the
  internals move, but the pin keeps that failure theoretical until
  a deliberate upgrade.

Bump deliberately (don't paper over with `>=`). Discuss in the PR
what downstream behaviour changed and whether `rebind_all`'s
internal-access check needs an update.

## Container / image changes

- The Dockerfile uses `uv sync --locked --no-dev --no-editable` —
  it pins from `uv.lock`, not from `pyproject.toml` re-resolution,
  to avoid silent bumps (an unpinned `pip install -e .` once pulled
  pydantic 2.13.x micro bumps that broke startup on this image's
  Python 3.11 while the dev environment — 3.13 — stayed green).
- The `astral-sh/uv` base image is digest-pinned; if you bump it,
  pin to the new digest in the same PR.

## Pull requests

- Title: a short imperative summary.
- Body: what changed, why, and any test or UX impact.
- Include the output of `uv run pytest` if behaviour changed.
- Link any relevant issue or `docs/superpowers/specs/*.md`.

## Issues

- Use the GitHub issue templates.
- For security issues, **do not** open a public issue — contact
  the maintainers directly.

## Coding agents

If you are an AI coding agent working on this repo, please also
read `AGENTS.md` (cross-tool) and `CLAUDE.md` (Claude Code). They
list the commands, conventions, and pin-discipline that human
contributors follow too.
