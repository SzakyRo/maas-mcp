"""machine_power_parameters: GET /machines/{system_id}/?op=power_parameters."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._machine_paths import machine_path, validate_system_id
from maasmcp.curated._resolve import resolve_system_id
from maasmcp.maas.client import MaasClient


class MachinePowerParametersTool:
    name = "machine_power_parameters"
    description = (
        "Read power parameters for a machine in MAAS. "
        "Use this for direct MAAS API access when no curated verb exists; call "
        "get_machine or list_machines to confirm the target first. "
        "Returns the machine's power parameters; for IPMI-type machines these "
        "include the BMC username and password. "
        "Accepts system_id or hostname (provide exactly one). "
        "Read-only; no confirmation needed."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        system_id: Annotated[
            str | None,
            Field(
                description="MAAS system_id of the machine. "
                "Provide this or hostname, exactly one."
            ),
        ] = None,
        *,
        hostname: Annotated[
            str | None,
            Field(description="Exact hostname of the machine; resolved to system_id server-side."),
        ] = None,
    ) -> dict[str, Any] | None:
        system_id = await resolve_system_id(client, system_id, hostname)
        validate_system_id(system_id)
        # ``op`` travels in the params dict, not the URL: httpx replaces the
        # URL query string wholesale when ``params=`` is passed, which would
        # silently drop an in-path ``?op=power_parameters``.
        params = {"op": "power_parameters"}
        return await client.get(  # type: ignore[no-any-return]
            machine_path(system_id),
            params=params,
        )
