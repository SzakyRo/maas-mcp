"""machines_accept: POST /api/2.0/machines/?op=accept."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._machine_paths import machines_op_path
from maasmcp.curated._resolve import resolve_hostnames
from maasmcp.maas.client import MaasClient


class MachinesAcceptTool:
    name = "machines_accept"
    description = (
        "Accept declared (New-state) machines into MAAS. Only works on machines "
        "awaiting enlistment approval; accepting an allocated or broken machine "
        "errors. Pass a list of system_ids to accept several at once (MAAS "
        "expects the 'machines' field repeated per system_id; an empty list is "
        "acceptable). "
        "Accepts system_ids or hostnames (union if both). Unlike the bulk fan-out "
        "verbs, accept is not per-host tolerant — any unmatched hostname raises "
        "ValueError (no silent partial acceptance). "
        "Returns the MAAS response. "
        "Admin-gated state change — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        machines: Annotated[
            list[str] | None,
            Field(
                description="List of system_ids of the machines whose enlistment "
                "is to be accepted. (An empty list is acceptable)."
            ),
        ] = None,
        *,
        hostnames: Annotated[
            list[str] | None,
            Field(
                description="List of exact hostnames; resolved with one fleet fetch. "
                "All hostnames must resolve — unmatched hostnames raise ValueError."
            ),
        ] = None,
        confirm: Annotated[
            bool,
            Field(description="Must be True to proceed. This operation is destructive."),
        ] = False,
    ) -> dict[str, Any] | list[dict[str, Any]] | None:
        if machines is None and hostnames is None:
            raise ValueError("must provide machines or hostnames (or both)")
        # Resolve hostnames (single fleet fetch) before the confirm gate so
        # addressing errors fail fast — tree-wide rule (T4 ruling).
        resolved = list(machines or [])
        if hostnames:
            mapping, missing = await resolve_hostnames(client, hostnames)
            if missing:
                raise ValueError(
                    f"no machine found with hostname(s) {missing!r}; "
                    "machines_accept does not accept a subset"
                )
            resolved.extend(mapping.values())
        # Back-compat: explicit empty inputs short-circuit before the gate so
        # callers that previously got `[]` from `machines=None` (no confirm)
        # keep working.
        if not resolved:
            return []
        if confirm is not True:
            raise ValueError(
                "machines_accept is destructive; pass confirm=True to proceed. "
                f"Affected: machines={len(machines or [])}, "
                f"hostnames={len(hostnames or [])}"
            )
        # list[str] values become repeated same-name multipart parts — the
        # exact shape MAAS documents for this op ("machines specified twice").
        params = {k: v for k, v in {"machines": resolved}.items() if v is not None}
        return await client.post(  # type: ignore[no-any-return]
            machines_op_path("accept"), json=params
        )
