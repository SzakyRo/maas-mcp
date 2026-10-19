"""get_space: GET /spaces/{id}/."""

from __future__ import annotations

from typing import Annotated, cast

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._network_paths import _validate_id, space_path
from maasmcp.curated._schemas.network import Space
from maasmcp.maas.client import MaasClient


class GetSpaceTool:
    name = "get_space"
    description = (
        "Fetch one MAAS space by its numeric id. "
        "Use this after list_spaces to discover ids. "
        "Returns the MAAS space dict (id, name, subnets/vlans if included). "
        "Read-only; no confirmation needed."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        space_id: Annotated[
            int, Field(description="MAAS id of the space (0 is the built-in 'undefined' space).")
        ],
    ) -> Space:
        _validate_id(space_id=space_id, _allow_zero=True)
        resp = await client.get(space_path(space_id))
        if not isinstance(resp, dict):
            raise ValueError(
                f"MAAS returned non-dict for space {space_id} "
                f"(got {type(resp).__name__}); schema drift?"
            )
        return cast(Space, resp)
