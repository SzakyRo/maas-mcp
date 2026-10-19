"""user_read: GET /api/2.0/users/{username}/."""

from __future__ import annotations

from typing import Annotated, cast

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._schemas.access import User
from maasmcp.curated._storage_paths import quote_segment
from maasmcp.maas.client import MaasClient


class UserReadTool:
    name = "user_read"
    description = (
        "Read a user in MAAS. "
        "Use this when you need the raw MAAS response or the curated verb does not exist. "
        "Returns the user object or result. "
        "Read-only; no confirmation needed."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        username: Annotated[str, Field(description="Username of the user to read.")],
    ) -> User | None:
        return cast(
            User | None,
            await client.get(f"/api/2.0/users/{quote_segment(username)}/"),
        )
