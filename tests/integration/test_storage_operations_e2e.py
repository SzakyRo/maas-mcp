"""Storage e2e round-trip: gated on MAASMCP_E2E_MAAS_URL.

Exercises list_block_devices → format_block_device on a real MAAS machine
that is in READY state. Skipped when MAASMCP_E2E_MAAS_URL is unset.
"""

from __future__ import annotations

import os

import pytest

from maasmcp.config import MaasmcpConfig
from maasmcp.curated.format_block_device import FormatBlockDeviceTool
from maasmcp.curated.list_block_devices import ListBlockDevicesTool
from maasmcp.maas.client import MaasClient

pytestmark = [
    pytest.mark.skipif(
        not os.environ.get("MAASMCP_E2E_MAAS_URL") or not os.environ.get("MAASMCP_E2E_SYSTEM_ID"),
        reason="MAASMCP_E2E_MAAS_URL and MAASMCP_E2E_SYSTEM_ID not set",
    ),
    pytest.mark.e2e,
]


@pytest.mark.asyncio
async def test_format_round_trip() -> None:
    """list_block_devices → format_block_device on the first device."""
    cfg = MaasmcpConfig.load(None)
    system_id = os.environ["MAASMCP_E2E_SYSTEM_ID"]
    async with MaasClient(cfg.maas) as client:
        client.base_url = cfg.maas.base_url  # type: ignore[attr-defined]
        devices = await ListBlockDevicesTool().run(client, system_id=system_id)
        assert devices, "machine has no block devices"
        await FormatBlockDeviceTool().run(
            client,
            system_id=system_id,
            block_device_id=devices[0]["id"],
            fstype="ext4",
            confirm=True,
        )
