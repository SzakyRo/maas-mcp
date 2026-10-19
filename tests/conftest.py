"""Shared pytest fixtures and configuration."""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _isolate_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear MAASMCP_* env vars so tests don't inherit ambient config."""
    for key in list(os.environ):
        if key.startswith("MAASMCP_") or key in {"MAAS_API_KEY", "MAAS_OAUTH_TOKEN"}:
            monkeypatch.delenv(key, raising=False)
