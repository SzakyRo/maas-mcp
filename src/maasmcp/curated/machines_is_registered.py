"""machines_is_registered: GET /machines/?op=is_registered."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.maas.client import MaasClient


class MachinesIsRegisteredTool:
    name = "machines_is_registered"
    description = (
        "Check whether a MAC address is registered in MAAS. "
        "Use this for direct MAAS API access when no curated verb exists. "
        "Returns whether the MAC address is registered. "
        "Read-only; no confirmation needed."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        mac_address: Annotated[str, Field(description="The MAC address to be checked.")],
    ) -> bool | None:
        # ``op`` goes in params (httpx would drop an in-path ``?op=`` when
        # ``params=`` is passed).
        params = {
            k: v
            for k, v in {"op": "is_registered", "mac_address": mac_address}.items()
            if v is not None
        }
        return await client.get(  # type: ignore[no-any-return]
            "/api/2.0/machines/",
            params=params,
        )
