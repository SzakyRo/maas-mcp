"""power_control: turn a machine on/off/cycle."""

from __future__ import annotations

import asyncio
from typing import Annotated, Any

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._machine_paths import machine_op_path, machine_path, validate_system_id
from maasmcp.curated._resolve import resolve_system_id
from maasmcp.maas.client import MaasClient

_ALLOWED = {"on", "off", "cycle"}
_CYCLE_DELAY_S = 5.0
_STOP_MODES = ("hard", "soft")

# MAAS returns Title-case status_name strings ("Deploying", "Commissioning").
# These are the states where the agent must refuse to power off — losing
# power mid-workflow can brick the machine or corrupt the install.
_BUSY_STATUSES = {"Deploying", "Commissioning"}


class PowerControlTool:
    name = "power_control"
    description = (
        "Power a machine on, off, or cycle it. "
        "'off' is a hard power off by default; pass stop_mode='soft' for a "
        "graceful OS shutdown request. 'cycle' is synthesized as power_off, a "
        "5s pause, then power_on (MAAS has no power_cycle op). "
        "Use after checking the current state with power_status when possible; "
        "refuses to power off machines that are in Deploying or Commissioning "
        "status. "
        "Returns the MAAS power action response, or None if MAAS replies with an empty body. "
        "Rejections raise ValueError (busy status or missing confirm). "
        "Accepts system_id or hostname (provide exactly one). "
        "DESTRUCTIVE — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        action: Annotated[
            str,
            Field(description="Power action to perform: on, off, or cycle."),
        ],
        stop_mode: Annotated[
            str,
            Field(
                description="Power-off mode for action='off'/'cycle': 'hard' (immediate, "
                "default) or 'soft' (graceful OS shutdown request)."
            ),
        ] = "hard",
        comment: Annotated[
            str | None, Field(description="Optional comment recorded on the power action.")
        ] = None,
        *,
        system_id: Annotated[
            str | None,
            Field(
                description="MAAS system_id of the machine. "
                "Provide this or hostname, exactly one."
            ),
        ] = None,
        hostname: Annotated[
            str | None,
            Field(description="Exact hostname of the machine; resolved to system_id server-side."),
        ] = None,
        confirm: Annotated[
            bool,
            Field(description="Must be True to proceed. This operation is destructive."),
        ] = False,
    ) -> dict[str, Any] | None:
        system_id = await resolve_system_id(client, system_id, hostname)
        validate_system_id(system_id)
        if action not in _ALLOWED:
            raise ValueError(f"action must be one of {sorted(_ALLOWED)}, got {action!r}")
        if stop_mode not in _STOP_MODES:
            raise ValueError(f"stop_mode must be one of {_STOP_MODES}, got {stop_mode!r}")
        if confirm is not True:
            raise ValueError(
                "power_control is destructive (cuts power immediately, even "
                "on Deployed machines); pass confirm=True to proceed. "
                f"Affected: system_id={system_id}, hostname={hostname}, action={action}"
            )

        if action in {"off", "cycle"}:
            # Refuse to power off a machine that's actively being worked on.
            machine = await client.get(machine_path(system_id))
            if isinstance(machine, dict):
                status = machine.get("status_name", "")
                if status in _BUSY_STATUSES:
                    raise ValueError(f"refusing to power off machine in {status!r} status")

        body: dict[str, Any] = {}
        if stop_mode != "hard":
            body["stop_mode"] = stop_mode
        if comment:
            body["comment"] = comment

        if action == "on":
            # stop_mode is a power_off concept; keep it out of the power_on body.
            on_body = {"comment": body["comment"]} if "comment" in body else None
            return await client.post(  # type: ignore[no-any-return]
                machine_op_path(system_id, "op-power_on"), json=on_body
            )
        if action == "off":
            return await client.post(  # type: ignore[no-any-return]
                machine_op_path(system_id, "op-power_off"), json=body or None
            )
        # cycle = power_off, brief pause, power_on
        await client.post(machine_op_path(system_id, "op-power_off"), json=body or None)
        await asyncio.sleep(_CYCLE_DELAY_S)
        return await client.post(  # type: ignore[no-any-return]
            machine_op_path(system_id, "op-power_on"),
            json={"comment": body["comment"]} if "comment" in body else None,
        )
