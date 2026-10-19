"""machines_list_allocated: GET /machines/?op=list_allocated."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.maas.client import MaasClient


class MachinesListAllocatedTool:
    name = "machines_list_allocated"
    description = (
        "List allocated machines in MAAS. "
        "Use this for direct MAAS API access when no curated verb exists; "
        "see list_machines for general machine enumeration. "
        "Returns a list of machine objects or the raw collection. "
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
    ) -> dict[str, Any] | list[dict[str, Any]] | None:
        # Strip the internal ``paginate`` flag before sending — MAAS
        # would treat it as a query param and 302-redirect us.
        # ``op`` goes in params (httpx would drop an in-path ``?op=`` when
        # ``params=`` is passed); ``paginate`` is local-only, never on the wire.
        params = {"op": "list_allocated"}
        return await client.paginated_get(  # type: ignore[no-any-return]
            "/api/2.0/machines/",
            params=params,
            paginate=paginate,
        )
