"""Tests for the maasmcp CLI."""

from __future__ import annotations

import os

from typer.testing import CliRunner

from maasmcp.cli import app

runner = CliRunner()


def test_root_help_lists_subcommands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "serve" in result.stdout


def test_serve_help() -> None:
    result = runner.invoke(app, ["serve", "--help"])
    assert result.exit_code == 0
    assert "--config" in result.stdout


def test_serve_rejects_missing_bearer_with_scrubbed_error(monkeypatch, tmp_path) -> None:
    """A validation error on `serve` must fail fast and must not echo input values.

    The `api_key` is a sensitive input. Default Pydantic ValidationError
    rendering includes `input=value` for every error, which leaks the key
    into startup logs. The CLI must scrub it.
    """
    # Isolate from the developer's real config: a top-level .env (loaded by
    # design for local runs) would otherwise satisfy the bearer requirement
    # and this test would actually boot uvicorn instead of validating.
    monkeypatch.chdir(tmp_path)
    for key in [k for k in os.environ if k.startswith("MAASMCP_")]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "super-secret-key")
    # No MAASMCP_SERVER__BEARER_TOKEN → ServerConfig validation fails.
    result = runner.invoke(app, ["serve"])
    assert result.exit_code != 0
    combined = (result.stdout or "") + (result.stderr or "")
    assert "super-secret-key" not in combined
    assert "bearer_token" in combined or "configuration" in combined.lower()
