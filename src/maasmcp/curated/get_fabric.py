"""get_fabric: GET /fabrics/{id}/."""

from __future__ import annotations

from typing import Annotated, cast

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._network_paths import _validate_id, fabric_path
from maasmcp.curated._schemas.network import Fabric
from maasmcp.maas.client import MaasClient


class GetFabricTool:
    name = "get_fabric"
    description = (
        "Fetch one fabric. "
        "Use this after list_fabrics to inspect a specific fabric's details. "
        "Returns the full MAAS fabric dict. "
        "Read-only; no confirmation needed."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        fabric_id: Annotated[int, Field(description="MAAS id of the fabric to fetch.")],
    ) -> Fabric:
        _validate_id(fabric_id=fabric_id, _allow_zero=True)
        resp = await client.get(fabric_path(fabric_id))
        if not isinstance(resp, dict):
            raise ValueError(
                f"MAAS returned non-dict for fabric {fabric_id} "
                f"(got {type(resp).__name__}); schema drift?"
            )
        return cast(Fabric, resp)
