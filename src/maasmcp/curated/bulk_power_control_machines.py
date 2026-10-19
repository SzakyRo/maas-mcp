"""bulk_power_control_machines: power on/off/cycle many hosts in parallel."""

from __future__ import annotations

import asyncio
from typing import Annotated, Any

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._fanout import _FANOUT_CONCURRENCY
from maasmcp.curated._machine_paths import machine_op_path, machine_path, validate_system_id
from maasmcp.curated._resolve import resolve_hostnames
from maasmcp.maas.client import MaasClient

_ALLOWED = {"on", "off", "cycle"}
_ACTION_TO_OP = {"on": "op-power_on", "off": "op-power_off"}
_CYCLE_DELAY_S = 5.0

# Mirror single-machine power_control.py: MAAS Title-case status_name
# values for hosts in active workflows. Cutting power on a Deploying or
# Commissioning host can brick the install.
_BUSY_STATUSES = {"Deploying", "Commissioning"}


class BulkPowerControlMachinesTool:
    name = "bulk_power_control_machines"
    description = (
        "Power on, off, or cycle multiple machines in parallel. "
        "Use this instead of repeated power_control calls for fleets; "
        "MAAS has no batch power endpoint, so this issues one POST per host "
        "(cap 10 in flight). 'cycle' is synthesized per host as power_off, a "
        "5s pause, then power_on — MAAS has no power_cycle op. 'off' is a hard "
        "power off. Hosts in Deploying or Commissioning status are skipped for "
        "off/cycle actions. "
        "Accepts system_ids or hostnames (union if both). Unmatched hostnames "
        "become per-host error entries. "
        "Returns a list of per-system_id entries with status ('ok'|'error') "
        "and an optional error message. "
        "DESTRUCTIVE — must pass confirm=True; rejected otherwise."
    )

    async def _power_one(
        self,
        client: MaasClient,
        system_id: str,
        action: str,
        sem: asyncio.Semaphore,
    ) -> dict[str, Any]:
        validate_system_id(system_id)
        async with sem:
            try:
                if action == "cycle":
                    # MAAS has no op-power_cycle; synthesize per host like the
                    # single-machine power_control does.
                    await client.post(machine_op_path(system_id, "op-power_off"))
                    await asyncio.sleep(_CYCLE_DELAY_S)
                    await client.post(machine_op_path(system_id, "op-power_on"))
                else:
                    await client.post(machine_op_path(system_id, _ACTION_TO_OP[action]))
                return {"system_id": system_id, "status": "ok", "result": None}
            except Exception as exc:
                return {"system_id": system_id, "status": "error", "error": str(exc)}

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        system_ids: Annotated[
            list[str] | None,
            Field(
                description="List of MAAS system_ids. Provide this or hostnames; "
                "union if both.",
                max_length=500,
            ),
        ] = None,
        *,
        hostnames: Annotated[
            list[str] | None,
            Field(
                description="List of exact hostnames; resolved with one fleet fetch.",
                max_length=500,
            ),
        ] = None,
        action: Annotated[str, Field(description="Power action to perform: on, off, or cycle.")],
        confirm: Annotated[
            bool, Field(description="Must be True to proceed. This operation is destructive.")
        ] = False,
    ) -> list[dict[str, Any]]:
        if action not in _ALLOWED:
            raise ValueError(f"action must be one of {sorted(_ALLOWED)}, got {action!r}")
        if system_ids is None and hostnames is None:
            raise ValueError("must provide system_ids or hostnames (or both)")
        # Resolve hostnames (single fleet fetch) before the confirm gate.
        resolved = list(system_ids or [])
        if hostnames:
            mapping, missing = await resolve_hostnames(client, hostnames)
            resolved.extend(mapping.values())
            missing_entries: list[dict[str, Any]] = [
                {
                    "system_id": h,
                    "status": "error",
                    "error": f"no machine found with hostname {h!r}",
                }
                for h in missing
            ]
        else:
            missing_entries = []
        # Validate explicitly-given system_ids (not hostname-resolved ones)
        # before the confirm gate so an invalid id surfaces its validation
        # error rather than the generic confirm-gate rejection.
        for sid in system_ids or []:
            validate_system_id(sid)
        # Back-compat: explicit empty inputs short-circuit before the gate.
        if not resolved and not missing_entries:
            return []
        if confirm is not True:
            raise ValueError(
                "bulk_power_control_machines is destructive (cuts power "
                "immediately across N hosts); pass confirm=True to proceed. "
                f"Affected: system_ids={system_ids}, hostnames={hostnames}, "
                f"action={action}"
            )
        # Mirror single-machine _BUSY_STATUSES check for off/cycle actions:
        # refuse to cut power on a host that's mid-deploy or mid-commission.
        if action in {"off", "cycle"}:
            busy_results = await asyncio.gather(
                *(client.get(machine_path(sid)) for sid in resolved),
                return_exceptions=True,
            )
            eligible: list[str] = []
            skipped: list[dict[str, Any]] = []
            for sid, m in zip(resolved, busy_results, strict=True):
                if isinstance(m, BaseException):
                    skipped.append(
                        {
                            "system_id": sid,
                            "status": "error",
                            "error": f"busy-status fetch failed: {m!r}",
                        }
                    )
                elif isinstance(m, dict) and m.get("status_name") in _BUSY_STATUSES:
                    skipped.append(
                        {
                            "system_id": sid,
                            "status": "error",
                            "error": f"refusing to power off machine in "
                            f"{m.get('status_name')!r} status",
                        }
                    )
                else:
                    eligible.append(sid)
        else:
            eligible = list(resolved)
            skipped = []
        sem = asyncio.Semaphore(_FANOUT_CONCURRENCY)
        raw = await asyncio.gather(
            *(self._power_one(client, sid, action, sem) for sid in eligible),
            return_exceptions=True,
        )
        # _power_one catches Exception, so any base exception here is
        # unexpected — re-raise it to preserve prior fail-fast behaviour.
        results: list[dict[str, Any]] = []
        for r in raw:
            if isinstance(r, dict):
                results.append(r)
            else:
                raise r
        # Reorder to match input order, then append the busy-status skips.
        by_sid = {item["system_id"]: item for item in results}
        ordered: list[dict[str, Any]] = []
        for sid in resolved:
            if sid in by_sid:
                ordered.append(by_sid[sid])
        return [*missing_entries, *ordered, *skipped]
