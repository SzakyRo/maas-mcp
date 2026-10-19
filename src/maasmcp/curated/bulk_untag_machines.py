"""bulk_untag_machines: remove a tag from many hosts via fan-out."""

from __future__ import annotations

import asyncio
from typing import Annotated

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._fanout import _FANOUT_CONCURRENCY
from maasmcp.curated._resolve import resolve_hostnames
from maasmcp.curated._schemas.access import BulkTagResult
from maasmcp.curated._storage_paths import quote_segment, validate_system_id
from maasmcp.maas.client import MaasClient


class BulkUntagMachinesTool:
    name = "bulk_untag_machines"
    description = (
        "Remove a tag from multiple machines in parallel. "
        "Use this instead of repeated untag_machine calls for fleets; mirrors "
        "bulk_tag_machines but uses the 'remove' body field. "
        "Accepts system_ids or hostnames (union if both). Unmatched hostnames "
        "become per-host error entries. "
        "Returns a list of per-system_id entries with status ('ok'|'error') "
        "and an optional error message. "
        "State-mutating across a fleet — must pass confirm=True; rejected otherwise."
    )

    async def _untag_one(
        self,
        client: MaasClient,
        tag: str,
        system_id: str,
        sem: asyncio.Semaphore,
    ) -> BulkTagResult:
        async with sem:
            try:
                await client.post(
                    f"/api/2.0/tags/{quote_segment(tag)}/op-update_nodes",
                    json={"remove": system_id},
                )
                return {"system_id": system_id, "status": "ok", "result": None}
            except Exception as exc:
                return {"system_id": system_id, "status": "error", "error": str(exc)}

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        system_ids: Annotated[
            list[str] | None,
            Field(
                description="List of MAAS system_ids. Provide this or hostnames; union if both.",
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
        tag: Annotated[str, Field(description="Tag name to remove from each machine.")],
        confirm: Annotated[
            bool, Field(description="Must be True to proceed. This operation mutates state.")
        ] = False,
    ) -> list[BulkTagResult]:
        if not tag:
            raise ValueError("tag must be a non-empty string")
        if system_ids is None and hostnames is None:
            raise ValueError("must provide system_ids or hostnames (or both)")
        # Resolve hostnames (single fleet fetch) before the confirm gate so
        # the gate can report counts and addressing errors fail fast.
        mapping: dict[str, str] = {}
        missing: list[str] = []
        if hostnames:
            mapping, missing = await resolve_hostnames(client, hostnames)
        # dict.fromkeys preserves first-occurrence order while dropping
        # duplicates — both for explicit system_ids (caller typed the same
        # id twice) and for hostname-resolved ids (same hostname in two
        # input slots, or MAAS returning duplicate hostnames in the fleet
        # listing). Without this, gather fans out duplicate tag-update
        # calls to the same machine.
        resolved = list(dict.fromkeys([*(system_ids or []), *mapping.values()]))
        missing_entries: list[BulkTagResult] = [
            {
                "system_id": h,
                "status": "error",
                "error": f"no machine found with hostname {h!r}",
            }
            for h in missing
        ]
        # Validate explicitly-given system_ids (not hostname-resolved ones)
        # before the confirm gate so an invalid id surfaces its validation
        # error rather than the generic confirm-gate rejection.
        for sid in system_ids or []:
            validate_system_id(sid)
        # Back-compat: explicit empty inputs short-circuit before the gate so
        # callers that previously got `[]` from `system_ids=[]` (no confirm)
        # keep working.
        if not resolved and not missing_entries:
            return []
        if confirm is not True:
            raise ValueError(
                "bulk_untag_machines mutates state across N hosts; pass confirm=True "
                f"to proceed. Affected: system_ids={system_ids}, "
                f"hostnames={hostnames}, tag={tag!r}"
            )
        sem = asyncio.Semaphore(_FANOUT_CONCURRENCY)
        raw = await asyncio.gather(
            *(self._untag_one(client, tag, sid, sem) for sid in resolved),
            return_exceptions=True,
        )
        # _untag_one catches Exception, so any base exception here is
        # unexpected — re-raise it to preserve prior fail-fast behaviour.
        results: list[BulkTagResult] = []
        for r in raw:
            if isinstance(r, dict):
                results.append(r)
            else:
                raise r
        return [*missing_entries, *results]
