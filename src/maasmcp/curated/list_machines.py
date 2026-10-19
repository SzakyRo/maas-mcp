"""list_machines: typed-filter list with a slim view."""

from __future__ import annotations

from fnmatch import fnmatch
from typing import Annotated, Any

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._schemas.base import MachineSlim
from maasmcp.maas.client import MaasClient


class ListMachinesTool:
    name = "list_machines"
    description = (
        "List machines in MAAS with typed filters. Use this to find "
        "candidates for acquire_machine, deploy_machine, or power_control. "
        "Server-side filters (zone, cpu_count_min, memory_min) reduce the "
        "MAAS payload; status/pool/tag/hostname_glob are filtered client-side. "
        "Returns a slim view: system_id, hostname, status_name, power_state, "
        "tag_names, pool. Read-only; no confirmation needed."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        status: Annotated[
            str | None, Field(description="Filter to machines with this status_name (client-side).")
        ] = None,
        pool: Annotated[
            str | None, Field(description="Filter to machines in this pool (client-side).")
        ] = None,
        tag: Annotated[
            str | None, Field(description="Filter to machines with this tag (client-side).")
        ] = None,
        hostname_glob: Annotated[
            str | None, Field(description="Filter to hostnames matching this glob (client-side).")
        ] = None,
        zone: Annotated[
            str | None, Field(description="Server-side filter: MAAS zone name.")
        ] = None,
        cpu_count_min: Annotated[
            int | None, Field(description="Server-side filter: minimum CPU count.")
        ] = None,
        memory_min: Annotated[
            int | None, Field(description="Server-side filter: minimum memory in MB.")
        ] = None,
    ) -> list[MachineSlim]:
        # Client-side status filtering, kept deliberately: the vendored doc
        # and current live MAAS accept ?status=..., but older releases have
        # rejected it with 400, so the curated verb filters on status_name
        # client-side. (The raw machines_read verb passes status through
        # for servers that support it.)
        params: dict[str, Any] = {}
        if zone:
            params["zone"] = zone
        if cpu_count_min is not None:
            params["cpu_count"] = cpu_count_min
        if memory_min is not None:
            params["mem"] = str(memory_min)
        # paginate=True: on MAAS versions that paginate /machines/, the
        # default page (~50) would silently drop machines beyond page 1.
        # On versions whose /machines/ is unpaginated, the pagination layer
        # falls back to a single full-list GET — see maas/paginated_get.py.
        machines: Any = await client.paginated_get(
            "/api/2.0/machines/", params=params, paginate=True
        )
        view: list[MachineSlim] = []
        if not isinstance(machines, list):
            return view
        for m in machines:
            if not isinstance(m, dict):
                continue
            if status and m.get("status_name") != status:
                continue
            if pool and (m.get("pool") or {}).get("name") != pool:
                continue
            if tag and tag not in (m.get("tag_names") or []):
                continue
            if hostname_glob and not fnmatch(m.get("hostname", ""), hostname_glob):
                continue
            row: MachineSlim = {
                "system_id": m.get("system_id"),
                "hostname": m.get("hostname"),
                "status_name": m.get("status_name"),
                "power_state": m.get("power_state"),
                "tag_names": m.get("tag_names", []),
                "pool": (m.get("pool") or {}).get("name"),
            }
            view.append(row)
        return view
