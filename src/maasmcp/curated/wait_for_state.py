"""wait_for_state: poll a machine until it reaches one of the target states."""

from __future__ import annotations

import asyncio
from typing import Annotated

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._machine_paths import machine_path, validate_system_id
from maasmcp.curated._resolve import resolve_system_id
from maasmcp.curated._schemas.machines import MachineRecord
from maasmcp.maas.client import MaasClient


class WaitForStateTool:
    name = "wait_for_state"
    description = (
        "Poll a machine until its status_name matches one of the target states. "
        "Use this after power_control, deploy_machine, release_machine, or other "
        "asynchronous operations to block until the machine reaches a known state. "
        "First call get_machine or list_machines to obtain the system_id and current state. "
        "Returns the final machine dict, including status_name and other machine fields. "
        "Accepts system_id or hostname (provide exactly one). "
        "Read-only; no confirmation needed."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        target_states: Annotated[
            list[str],
            Field(
                description=(
                    "List of status_name values that satisfy the wait "
                    "(e.g. ['Ready', 'Deployed']). The wait completes when the machine "
                    "matches any one of them."
                )
            ),
        ],
        *,
        system_id: Annotated[
            str | None,
            Field(
                description="MAAS system_id of the machine to poll. "
                "Provide this or hostname, exactly one."
            ),
        ] = None,
        hostname: Annotated[
            str | None,
            Field(description="Exact hostname of the machine; resolved to system_id server-side."),
        ] = None,
        timeout_seconds: Annotated[
            int,
            Field(description="Maximum time to wait, in seconds, before raising TimeoutError."),
        ] = 600,
        poll_interval_seconds: Annotated[
            float, Field(description="Seconds to sleep between polls.")
        ] = 5.0,
    ) -> MachineRecord:
        system_id = await resolve_system_id(client, system_id, hostname)
        validate_system_id(system_id)
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        while True:
            machine = await client.get(machine_path(system_id))
            if isinstance(machine, dict) and machine.get("status_name") in target_states:
                return machine  # type: ignore[return-value]
            if asyncio.get_running_loop().time() >= deadline:
                # TimeoutError, not MCPUpstreamTimeout: the MAAS upstream is
                # healthy — we simply gave up waiting. Raising an upstream
                # error type would mis-signal a MAAS outage.
                raise TimeoutError(
                    f"machine {system_id} did not reach {target_states} within {timeout_seconds}s"
                )
            await asyncio.sleep(poll_interval_seconds)
