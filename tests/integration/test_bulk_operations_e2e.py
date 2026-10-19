# tests/integration/test_bulk_operations_e2e.py
"""Bulk operations against a real MAAS. Gated on MAASMCP_E2E_MAAS_URL env var."""

from __future__ import annotations

import os

import pytest

from maasmcp.config import MaasmcpConfig
from maasmcp.curated.bulk_tag_machines import BulkTagMachinesTool
from maasmcp.curated.bulk_untag_machines import BulkUntagMachinesTool
from maasmcp.maas.client import MaasClient

E2E_URL = os.environ.get("MAASMCP_E2E_MAAS_URL")
pytestmark = [
    pytest.mark.skipif(not E2E_URL, reason="MAASMCP_E2E_MAAS_URL not set"),
    pytest.mark.e2e,
]


@pytest.fixture
def maas_client() -> MaasClient:
    cfg = MaasmcpConfig.load(None)
    cfg.maas.base_url = E2E_URL  # type: ignore[attr-defined]
    return MaasClient(cfg.maas)


@pytest.mark.asyncio
async def test_bulk_tag_round_trip(maas_client: MaasClient) -> None:
    """Tag a freshly-discovered READY machine with a unique tag, then untag."""
    import uuid

    tag = f"e2e-{uuid.uuid4().hex[:8]}"
    async with maas_client:
        # MAAS rejects ?status= on /machines/ (400 for every variant) —
        # paginate the collection and filter on status_name client-side.
        listed = await maas_client.paginated_get("/api/2.0/machines/", paginate=True)
        ready = [m for m in listed if isinstance(m, dict) and m.get("status_name") == "Ready"]
        assert ready, "no Ready machines in this MAAS"
        system_id = ready[0]["system_id"]

        tag_result = await BulkTagMachinesTool().run(
            maas_client, system_ids=[system_id], tag=tag, confirm=True
        )
        assert tag_result[0]["status"] == "ok", tag_result

        machine = await maas_client.get(f"/api/2.0/machines/{system_id}/")
        assert tag in (machine.get("tag_names") or []), machine

        untag_result = await BulkUntagMachinesTool().run(
            maas_client, system_ids=[system_id], tag=tag, confirm=True
        )
        assert untag_result[0]["status"] == "ok", untag_result
