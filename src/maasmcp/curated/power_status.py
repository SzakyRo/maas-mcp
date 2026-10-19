"""power_status: read a machine's current power state."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._machine_paths import machine_path, validate_system_id
from maasmcp.curated._resolve import resolve_system_id
from maasmcp.maas.client import MaasClient


class PowerStatusTool:
    name = "power_status"
    description = (
        "Return the current power state of a machine (cheap, cached read of the "
        "machine record's power_state: 'on', 'off', 'unknown', or 'error'). "
        "Use before power_control to verify state. Note: this is MAAS's last-known "
        "state, not a live probe — MAAS's live BMC probe (op-query_power_state) can "
        "hang badly-configured BMCs, so this tool intentionally prefers the cached "
        "field, which may lag a recent power action by a few seconds. "
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
    ) -> str:
        system_id = await resolve_system_id(client, system_id, hostname)
        validate_system_id(system_id)
        machine = await client.get(machine_path(system_id))
        if not isinstance(machine, dict):
            raise ValueError(f"unexpected response for machine {system_id}")
        power_state = machine.get("power_state", "unknown")
        return str(power_state)
