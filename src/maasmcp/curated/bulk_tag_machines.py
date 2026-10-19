"""bulk_tag_machines: add a tag to many hosts via asyncio.gather fan-out."""

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


class BulkTagMachinesTool:
    name = "bulk_tag_machines"
    description = (
        "Add a tag to multiple machines in parallel. "
        "Use this instead of repeated tag_machine calls for fleets; MAAS has "
        "no batch tag endpoint, so this issues one POST per host (cap 10 "
        "in flight). "
        "Accepts system_ids or hostnames (union if both). Unmatched hostnames "
        "become per-host error entries (the BulkTagResult schema tolerates the "
        "raw hostname string in its system_id field). "
        "Returns a list of per-system_id entries with status ('ok'|'error') "
        "and an optional error message. "
        "State-mutating across a fleet — must pass confirm=True; rejected otherwise."
    )

    async def _tag_one(
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
                    json={"add": system_id},
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
        tag: Annotated[str, Field(description="Tag name to add to each machine.")],
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
        resolved = list(system_ids or [])
        if hostnames:
            mapping, missing = await resolve_hostnames(client, hostnames)
            resolved.extend(mapping.values())
            missing_entries: list[BulkTagResult] = [
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
        # Back-compat: explicit empty inputs short-circuit before the gate so
        # callers that previously got `[]` from `system_ids=[]` (no confirm)
        # keep working.
        if not resolved and not missing_entries:
            return []
        if confirm is not True:
            raise ValueError(
                "bulk_tag_machines mutates state across N hosts; pass confirm=True "
                f"to proceed. Affected: system_ids={system_ids}, "
                f"hostnames={hostnames}, tag={tag!r}"
            )
        sem = asyncio.Semaphore(_FANOUT_CONCURRENCY)
        raw = await asyncio.gather(
            *(self._tag_one(client, tag, sid, sem) for sid in resolved),
            return_exceptions=True,
        )
        # _tag_one catches Exception, so any base exception here is unexpected;
        # re-raise it to preserve prior fail-fast behaviour.
        results: list[BulkTagResult] = []
        for r in raw:
            if isinstance(r, dict):
                results.append(r)
            else:
                raise r
        return [*missing_entries, *results]
