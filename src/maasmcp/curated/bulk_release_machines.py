"""bulk_release_machines: release (deallocate) many machines in parallel."""

from __future__ import annotations

import asyncio
from typing import Annotated, Any

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._fanout import _FANOUT_CONCURRENCY
from maasmcp.curated._machine_paths import machine_op_path, validate_system_id
from maasmcp.curated._resolve import resolve_hostnames
from maasmcp.maas.client import MaasClient


class BulkReleaseMachinesTool:
    name = "bulk_release_machines"
    description = (
        "Release (deallocate) multiple machines back to the pool, fanning out "
        "one per-machine op-release call per host (cap 10 in flight). "
        "MAAS's collection op-release only accepts a machine list and a comment, "
        "so the erase/secure_erase/quick_erase/force options are applied via "
        "per-machine calls where MAAS honors them. "
        "Use this instead of repeated release_machine calls when returning "
        "many hosts at once; for a single host use release_machine. "
        "Accepts system_ids or hostnames (union if both). Unmatched hostnames "
        "become per-host error entries. "
        "Returns a list of per-system_id entries with status ('ok'|'error'), "
        "and either a result dict or an error message. "
        "DESTRUCTIVE — must pass confirm=True; rejected otherwise. Disks are "
        "erased by default (erase=true)."
    )

    async def _release_one(
        self,
        client: MaasClient,
        system_id: str,
        data: dict[str, Any],
        sem: asyncio.Semaphore,
    ) -> dict[str, Any]:
        async with sem:
            try:
                result = await client.post(machine_op_path(system_id, "op-release"), json=data)
                return {"system_id": system_id, "status": "ok", "result": result}
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
        comment: Annotated[
            str | None, Field(description="Optional comment recorded on the release action.")
        ] = None,
        erase: Annotated[
            bool, Field(description="Whether to erase disks on release (default true).")
        ] = True,
        secure_erase: Annotated[
            bool, Field(description="Use secure erase when erasing disks.")
        ] = False,
        quick_erase: Annotated[
            bool, Field(description="Use quick erase when erasing disks.")
        ] = False,
        force: Annotated[
            bool,
            Field(
                description="Force release even if the machine is in a non-releasable state "
                "(e.g. a deployed KVM host — its hosted VMs are deleted too)."
            ),
        ] = False,
        confirm: Annotated[
            bool, Field(description="Must be True to proceed. This operation is destructive.")
        ] = False,
    ) -> list[dict[str, Any]]:
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
                "bulk_release_machines is destructive (securely erases disks "
                "by default across N hosts); pass confirm=True to proceed. "
                f"Affected: system_ids={system_ids}, hostnames={hostnames}, "
                f"erase={erase}"
            )
        data: dict[str, Any] = {
            "erase": erase,
            "secure_erase": secure_erase,
            "quick_erase": quick_erase,
        }
        if force:
            data["force"] = True
        if comment:
            data["comment"] = comment
        sem = asyncio.Semaphore(_FANOUT_CONCURRENCY)
        raw = await asyncio.gather(
            *(self._release_one(client, sid, data, sem) for sid in resolved),
            return_exceptions=True,
        )
        # _release_one catches Exception; a base exception here is unexpected —
        # re-raise to preserve fail-fast behaviour.
        results: list[dict[str, Any]] = []
        for r in raw:
            if isinstance(r, dict):
                results.append(r)
            else:
                raise r
        # Reorder to match input order, then append the hostname misses.
        by_sid = {item["system_id"]: item for item in results}
        ordered: list[dict[str, Any]] = [by_sid[sid] for sid in resolved if sid in by_sid]
        return [*ordered, *missing_entries]
