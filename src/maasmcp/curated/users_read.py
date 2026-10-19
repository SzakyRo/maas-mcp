"""users_read: GET /api/2.0/users/."""

from __future__ import annotations

from typing import Annotated, Any, cast

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._schemas.access import User
from maasmcp.maas.client import MaasClient


class UsersReadTool:
    name = "users_read"
    description = (
        "Read users in MAAS. "
        "Alias of users_list (identical GET /users/ collection read, kept for "
        "client compatibility) — prefer users_list. "
        "Returns a list of user objects or the raw collection. "
        "Read-only; no confirmation needed."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        paginate: Annotated[
            bool,
            Field(
                description="Set to True to auto-paginate through limit/offset up to max_paginated_items. False (default) returns a single MAAS page."
            ),
        ] = False,
    ) -> list[User] | dict[str, Any] | None:
        # ``paginate`` is local-only — sending it as a query param would
        # trigger a MAAS 302 redirect.
        params: dict[str, Any] = {}
        return cast(
            list[User] | dict[str, Any] | None,
            await client.paginated_get("/api/2.0/users/", params=params, paginate=paginate),
        )
