"""Tests for MaasmcpConfig loading."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from pydantic import ValidationError

from maasmcp.config import MaasConfig, MaasmcpConfig, MaasmcpSettingsSource


def test_load_from_yaml_with_env_expansion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAAS_API_KEY", "secret-key")
    monkeypatch.setenv("MAASMCP_BEARER_TOKEN", "bearer-secret-0123")
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "maas:\n"
        "  base_url: https://maas.example.com/MAAS\n"
        "  api_key: ${MAAS_API_KEY}\n"
        "  api_version: '2.0'\n"
        "  verify_tls: true\n"
        "server:\n"
        "  host: 127.0.0.1\n"
        "  port: 9001\n"
        "  bearer_token: ${MAASMCP_BEARER_TOKEN}\n"
        "  log_level: debug\n"
        "  request_timeout_seconds: 30\n"
        "  max_paginated_items: 500\n"
    )
    cfg = MaasmcpConfig.load(config_file)
    assert cfg.maas.base_url == "https://maas.example.com/MAAS"
    assert cfg.maas.api_key == "secret-key"
    assert cfg.server.bearer_token == "bearer-secret-0123"
    assert cfg.server.port == 9001
    assert cfg.server.max_paginated_items == 500


def test_missing_var_in_yaml_raises(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "maas:\n  base_url: https://maas.example.com/MAAS\n  api_key: ${MISSING_VAR}\n"
    )
    with pytest.raises(RuntimeError, match="MISSING_VAR"):
        MaasmcpConfig.load(config_file)


def test_missing_yaml_falls_back_to_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "env-token-01234567")
    cfg = MaasmcpConfig.load(None)
    assert cfg.maas.base_url == "https://maas.example.com/MAAS"
    assert cfg.maas.api_key == "k"
    assert cfg.server.bearer_token == "env-token-01234567"


def test_invalid_port_raises(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "maas:\n  base_url: https://maas.example.com/MAAS\n  api_key: x\n"
        "server:\n  bearer_token: valid-token-012345\n  port: 99999\n"
    )
    with pytest.raises(ValidationError):
        MaasmcpConfig.load(config_file)


def test_empty_bearer_token_rejected(tmp_path: Path) -> None:
    """An empty expected token would authenticate headerless requests
    (hmac.compare_digest("...", "") == (no header)); short tokens are the
    operator's call, empty is not."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "maas:\n  base_url: https://maas.example.com/MAAS\n  api_key: x\n"
        "server:\n  bearer_token: ''\n"
    )
    with pytest.raises(ValidationError):
        MaasmcpConfig.load(config_file)


def test_short_bearer_token_accepted(tmp_path: Path) -> None:
    """Short tokens are permitted — trusted-network deployments use them."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "maas:\n  base_url: https://maas.example.com/MAAS\n  api_key: x\n"
        "server:\n  bearer_token: stronk\n"
    )
    assert MaasmcpConfig.load(config_file).server.bearer_token == "stronk"


def test_settings_source_present() -> None:
    """The custom settings source must be registered so env vars override YAML."""
    sources = MaasmcpConfig.settings_customise_sources(
        MaasmcpConfig,  # type: ignore[arg-type]
        MaasmcpSettingsSource,
        *[],  # type: ignore[list-item]
    )
    # MaasmcpSettingsSource must appear in the returned tuple
    assert any(isinstance(s, MaasmcpSettingsSource) for s in sources)


def test_triple_api_key_splits_into_oauth_fields() -> None:
    """A 3-part ``consumer:token:token_secret`` api_key is normalized to OAuth.

    MAAS issues API keys as ``"<consumer_key>:<token_key>:<token_secret>"``
    with an empty consumer_secret. The MaasConfig validator splits that
    into the four OAuth credential fields and clears api_key.
    """
    cfg = MaasConfig(
        base_url="https://maas.example.com/MAAS",
        api_key="ck:tk:ts",
    )
    assert cfg.api_key is None
    assert cfg.consumer_key == "ck"
    assert cfg.consumer_secret == ""
    assert cfg.token_key == "tk"
    assert cfg.token_secret == "ts"


def test_single_part_api_key_stays_bearer() -> None:
    """A plain opaque key (no colons) is left as a Bearer token."""
    cfg = MaasConfig(
        base_url="https://maas.example.com/MAAS",
        api_key="opaque-key",
    )
    assert cfg.api_key == "opaque-key"
    assert cfg.consumer_key is None


def test_explicit_oauth_fields_override_triple_split() -> None:
    """If user already supplies OAuth fields, the api_key is left as Bearer."""
    cfg = MaasConfig(
        base_url="https://maas.example.com/MAAS",
        api_key="leftover-bearer-value",
        consumer_key="real_ck",
        token_key="real_tk",
        token_secret="real_ts",
    )
    # Triple-shape detection skipped because OAuth fields are populated.
    assert cfg.api_key == "leftover-bearer-value"
    assert cfg.consumer_key == "real_ck"


def test_triple_api_key_routes_to_oauth_mode() -> None:
    """Triple api_key resolves to OAuth auth mode in MaasClient."""
    from maasmcp.maas.client import MaasClient

    cfg = MaasConfig(
        base_url="https://maas.example.com/MAAS",
        api_key="ck:tk:ts",
    )

    async def run() -> str:
        async with MaasClient(cfg) as c:
            return c._auth_mode  # type: ignore[attr-defined]

    assert asyncio.run(run()) == "oauth"


def test_empty_bearer_token_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Security gate: an empty bearer token would authenticate headerless
    requests — refuse it at config load."""
    import pydantic

    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "")
    with pytest.raises(pydantic.ValidationError):
        MaasmcpConfig.load(None)
