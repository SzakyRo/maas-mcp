"""update_fabric: PUT /fabrics/{id}/."""

from __future__ import annotations

from typing import Annotated, Any, cast

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._network_paths import _validate_id, fabric_path
from maasmcp.curated._schemas.network import Fabric
from maasmcp.maas.client import MaasClient


class UpdateFabricTool:
    name = "update_fabric"
    description = (
        "Update a fabric's name, description, or class type. "
        "Use this to rename or reclassify an existing fabric; create a new "
        "fabric with create_fabric. "
        "Returns the updated fabric dict. "
        "DESTRUCTIVE — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        fabric_id: Annotated[int, Field(description="MAAS id of the fabric to update.")],
        name: Annotated[str | None, Field(description="New fabric name.")] = None,
        description: Annotated[str | None, Field(description="New fabric description.")] = None,
        class_type: Annotated[str | None, Field(description="New fabric class_type value.")] = None,
        confirm: Annotated[
            bool,
            Field(description="Must be True to proceed. This operation is destructive."),
        ] = False,
    ) -> Fabric:
        _validate_id(fabric_id=fabric_id, _allow_zero=True)
        if confirm is not True:
            raise ValueError(
                "update_fabric is destructive; pass confirm=True to proceed. "
                f"Affected: fabric_id={fabric_id}"
            )
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if description is not None:
            body["description"] = description
        if class_type is not None:
            body["class_type"] = class_type
        resp = await client.put(fabric_path(fabric_id), json=body)
        if not isinstance(resp, dict):
            raise ValueError(
                f"MAAS returned non-dict for updated fabric "
                f"(got {type(resp).__name__}); schema drift?"
            )
        return cast(Fabric, resp)
