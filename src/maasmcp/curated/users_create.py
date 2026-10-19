"""users_create: POST /api/2.0/users/."""

from __future__ import annotations

from typing import Annotated, cast

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._schemas.access import User
from maasmcp.maas.client import MaasClient


class UsersCreateTool:
    name = "users_create"
    description = (
        "Create a user in MAAS. WARNING per the MAAS docs: the password is sent "
        "in plaintext — avoid for production unless you can prevent eavesdropping "
        "on the request. "
        "Use this for direct MAAS API access when no curated verb exists; "
        "see users_list and user_read to inspect existing users. "
        "Returns the MAAS response. "
        "DESTRUCTIVE — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        username: Annotated[str, Field(description="Identifier-style username for the new user.")],
        email: Annotated[str, Field(description="Email address for the new user.")],
        password: Annotated[str, Field(description="Password for the new user.")],
        is_superuser: Annotated[
            bool,
            Field(description="Whether the new user is to be an administrator."),
        ],
        confirm: Annotated[
            bool, Field(description="Must be True to proceed. This operation is destructive.")
        ] = False,
    ) -> User | None:
        if confirm is not True:
            raise ValueError(
                "users_create is destructive; pass confirm=True to proceed. "
                f"Affected: username={username}"
            )
        body = {
            k: v
            for k, v in {
                "username": username,
                "email": email,
                "password": password,
                "is_superuser": is_superuser,
            }.items()
            if v is not None
        }
        return cast(User | None, await client.post("/api/2.0/users/", json=body))
