"""get_vlan: GET /fabrics/{fabric_id}/vlans/{vid}/.

The ``vid`` parameter is the IEEE 802.1Q VLAN identifier (e.g. 79),
NOT MAAS's internal primary key. MAAS's VLAN endpoints are fabric-scoped
(``/api/2.0/fabrics/{fabric_id}/vlans/{vid}/``), so both fabric_id and vid
are required to build the URL.
"""

from __future__ import annotations

from typing import Annotated, cast

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._network_paths import _validate_id, vlan_path
from maasmcp.curated._schemas.network import Vlan
from maasmcp.maas.client import MaasClient


class GetVlanTool:
    name = "get_vlan"
    description = (
        "Fetch one VLAN by fabric_id and 802.1Q VLAN id (vid). "
        "Both arguments are REQUIRED — MAAS VLAN endpoints are "
        "fabric-scoped (/api/2.0/fabrics/{fabric_id}/vlans/{vid}/). "
        "Do NOT pass MAAS's internal VLAN primary key (the integer "
        "that comes back as `vlan.id` from list_subnets / interfaces) "
        "here: that id is not a URL segment. To look up a VLAN by its "
        "internal id, use list_subnets first (the embedded "
        "`vlan: {id, vid, fabric_id}` shape gives you both pieces) or "
        "use network_layout, which assembles the (fabric_id, vid) "
        "translation for you. Returns the MAAS VLAN dict. "
        "Read-only; no confirmation needed."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        fabric_id: Annotated[int, Field(description="MAAS id of the fabric that owns the VLAN.")],
        vid: Annotated[
            int, Field(description="IEEE 802.1Q VLAN ID (vid) within the fabric, e.g. 79.")
        ],
    ) -> Vlan:
        _validate_id(fabric_id=fabric_id, _allow_zero=True)
        resp = await client.get(vlan_path(fabric_id, vid))
        if not isinstance(resp, dict):
            raise ValueError(
                f"MAAS returned non-dict for vlan fabric={fabric_id} vid={vid} "
                f"(got {type(resp).__name__}); schema drift?"
            )
        return cast(Vlan, resp)
