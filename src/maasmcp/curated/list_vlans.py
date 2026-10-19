"""list_vlans: GET /fabrics/{fabric_id}/vlans/.

VLANs are fabric-scoped in MAAS — there is no global /vlans/ collection
endpoint. Callers must know which fabric they want VLANs for; iterate
across fabrics via ``list_fabrics`` if cluster-wide coverage is needed.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._network_paths import _validate_id, vlans_path
from maasmcp.curated._schemas.network import Vlan
from maasmcp.maas.client import MaasClient


class ListVlansTool:
    name = "list_vlans"
    description = (
        "List VLANs on a fabric. VLANs are fabric-scoped in MAAS, so call "
        "list_fabrics first to enumerate fabric IDs. Use this before "
        "create_vlan, update_vlan, or delete_vlan. Returns a list of VLAN "
        "dicts. Read-only; no confirmation needed."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        fabric_id: Annotated[int, Field(description="ID of the fabric whose VLANs to list.")],
    ) -> list[Vlan]:
        _validate_id(fabric_id=fabric_id, _allow_zero=True)
        resp = await client.get(vlans_path(fabric_id))
        if isinstance(resp, dict) and "vlans" in resp:
            return list(resp["vlans"])
        if isinstance(resp, list):
            return resp
        return []
