"""user_delete: DELETE /api/2.0/users/{username}/."""

from __future__ import annotations

import urllib.parse
from typing import Annotated

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._storage_paths import quote_segment
from maasmcp.maas.client import MaasClient


class UserDeleteTool:
    name = "user_delete"
    description = (
        "Delete a user in MAAS. "
        "Use this for direct MAAS API access when no curated verb exists. "
        "Returns nothing on success. "
        "DESTRUCTIVE — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        username: Annotated[str, Field(description="Username of the user to delete.")],
        transfer_resources_to: Annotated[
            str | None,
            Field(
                description="An optional username. If supplied, the allocated resources of the user being deleted will be transferred to this user. A user can't be removed unless its resources (machines, IP addresses, ...), are released or transfered to another user."
            ),
        ] = None,
        confirm: Annotated[
            bool, Field(description="Must be True to proceed. This operation is destructive.")
        ] = False,
    ) -> None:
        if confirm is not True:
            raise ValueError(
                "user_delete is destructive; pass confirm=True to proceed. "
                f"Affected: username={username}, transfer_resources_to={transfer_resources_to!r}"
            )
        path = f"/api/2.0/users/{quote_segment(username)}/"
        if transfer_resources_to is not None:
            # transfer_resources_to is a real MAAS query param; MaasClient.delete
            # takes no params, so send it inline in the path query string —
            # URL-encoded so a username containing &, #, ?, % or whitespace
            # can't corrupt the query.
            path = (
                f"{path}?transfer_resources_to={urllib.parse.quote(transfer_resources_to, safe='')}"
            )
        await client.delete(path)
