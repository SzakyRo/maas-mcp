"""create_fabric: POST /fabrics/."""

from __future__ import annotations

from typing import Annotated, Any, cast

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._network_paths import fabrics_path
from maasmcp.curated._schemas.network import Fabric
from maasmcp.maas.client import MaasClient


class CreateFabricTool:
    name = "create_fabric"
    description = (
        "Create a fabric in MAAS. "
        "Use this as the first step when building a new network topology; "
        "fabrics contain VLANs and subnets that are attached to machines. "
        "Returns the newly-created fabric dict. "
        "DESTRUCTIVE (cluster-wide) — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        name: Annotated[str, Field(description="Name for the new fabric.")],
        description: Annotated[
            str | None, Field(description="Optional human-readable description.")
        ] = None,
        class_type: Annotated[
            str | None, Field(description="Optional fabric class/type identifier.")
        ] = None,
        confirm: Annotated[
            bool, Field(description="Must be True to proceed. This operation is destructive.")
        ] = False,
    ) -> Fabric:
        if confirm is not True:
            raise ValueError(
                f"create_fabric is destructive; pass confirm=True to proceed. Affected: name={name}"
            )
        body: dict[str, Any] = {"name": name}
        if description is not None:
            body["description"] = description
        if class_type is not None:
            body["class_type"] = class_type
        resp = await client.post(fabrics_path(), json=body)
        if not isinstance(resp, dict):
            raise ValueError(
                f"MAAS returned non-dict for created fabric "
                f"(got {type(resp).__name__}); schema drift?"
            )
        return cast(Fabric, resp)
