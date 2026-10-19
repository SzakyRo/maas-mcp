"""machines_power_parameters: GET /machines/?op=power_parameters."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.maas.client import MaasClient


class MachinesPowerParametersTool:
    name = "machines_power_parameters"
    description = (
        "Read power parameters for machines in MAAS. "
        "Use this for direct MAAS API access when no curated verb exists. "
        "Returns the power parameters for the matching machines; note these "
        "include BMC/IPMI credentials. "
        "Read-only; no confirmation needed."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        id: Annotated[
            str,
            Field(
                description="System ID of the machine whose power parameters to read. "
                "(MAAS accepts multiple id params; this tool takes one — call "
                "machine_power_parameters for repeated use.)"
            ),
        ],
    ) -> dict[str, Any] | None:
        # ``op`` goes in params (httpx would drop an in-path ``?op=`` when
        # ``params=`` is passed).
        params = {k: v for k, v in {"op": "power_parameters", "id": id}.items() if v is not None}
        return await client.get(  # type: ignore[no-any-return]
            "/api/2.0/machines/",
            params=params,
        )
