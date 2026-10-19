"""users_list: GET /api/2.0/users/."""

from __future__ import annotations

from typing import Annotated, Any, cast

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._schemas.access import User
from maasmcp.maas.client import MaasClient


class UsersListTool:
    name = "users_list"
    description = (
        "List users in MAAS. "
        "Use this to discover usernames before user_read / user_delete / "
        "users_create. (users_read is an identical alias kept for client "
        "compatibility — prefer this one.) "
        "Returns a list of user objects (or a single page unless paginate=True). "
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
