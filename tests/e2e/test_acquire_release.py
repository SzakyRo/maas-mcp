"""E2E: acquire a real MAAS machine, then release it. Requires live MAAS."""

from __future__ import annotations

import os

import pytest

from maasmcp.config import MaasConfig, MaasmcpConfig, ServerConfig
from maasmcp.curated.acquire_machine import AcquireMachineTool
from maasmcp.curated.release_machine import ReleaseMachineTool
from maasmcp.maas.client import MaasClient

# Capture env at import time. The parent tests/conftest.py installs an
# autouse fixture that strips MAASMCP_* env vars per-test, so by the time
# the test body runs those keys are gone. Snapshotting them here lets
# the test actually attempt the HTTP call (and fail with a connection
# error) instead of crashing on KeyError.
_E2E_URL = os.environ.get("MAASMCP_E2E_URL", "")
_E2E_KEY = os.environ.get("MAASMCP_E2E_KEY", "")

_e2e_skipif = pytest.mark.skipif(
    not (_E2E_URL and _E2E_KEY),
    reason="MAASMCP_E2E_URL and MAASMCP_E2E_KEY not set",
)
pytestmark = [_e2e_skipif, pytest.mark.e2e]


def _config() -> MaasmcpConfig:
    return MaasmcpConfig(
        maas=MaasConfig(base_url=_E2E_URL, api_key=_E2E_KEY),
        server=ServerConfig(bearer_token="unused-e2e-token-012"),
    )


@pytest.mark.asyncio
async def test_acquire_then_release_round_trip() -> None:
    cfg = _config()
    async with MaasClient(cfg.maas) as client:
        # Status filter is Title-case ("Ready"), matching status_name — the
        # tools filter client-side because MAAS rejects ?status= on /machines/.
        acquired = await AcquireMachineTool().run(client, status="Ready", confirm=True)
        assert acquired["system_id"]
        released = await ReleaseMachineTool().run(
            client, system_id=acquired["system_id"], erase=False, confirm=True
        )
        assert released is not None
