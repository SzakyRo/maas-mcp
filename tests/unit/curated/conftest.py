"""Shared fixtures for tests/unit/curated/.

The `maas_client` fixture used to be copy-pasted (in two variants differing
only by docstring) into every tool test file; it lives here once.
"""

from __future__ import annotations

import pytest

from maasmcp.config import MaasmcpConfig
from maasmcp.maas.client import MaasClient


@pytest.fixture
def maas_client(monkeypatch: pytest.MonkeyPatch) -> MaasClient:
    """Build a MaasClient with the same env-var setup used in test_config.py.

    tests/conftest.py autouses an env-clear; we restore the minimum required
    keys here. base_url is exposed on the instance for respx to target.
    """
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "curated-test-token-01")
    cfg = MaasmcpConfig.load(None)
    client = MaasClient(cfg.maas)
    client.base_url = cfg.maas.base_url  # type: ignore[attr-defined]
    return client
