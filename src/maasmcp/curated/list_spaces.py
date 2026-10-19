"""list_spaces: GET /spaces/."""

from __future__ import annotations

from typing import Annotated

from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._network_paths import spaces_path
from maasmcp.curated._schemas.network import Space
from maasmcp.maas.client import MaasClient


class ListSpacesTool:
    name = "list_spaces"
    description = (
        "List all spaces in MAAS. Use this before create_space, "
        "update_space, or delete_space. Returns a list of space dicts. "
        "Read-only; no confirmation needed."
    )

    async def run(self, client: Annotated[MaasClient, SkipJsonSchema()]) -> list[Space]:
        resp = await client.get(spaces_path())
        if isinstance(resp, dict) and "spaces" in resp:
            return list(resp["spaces"])
        if isinstance(resp, list):
            return resp
        return []
