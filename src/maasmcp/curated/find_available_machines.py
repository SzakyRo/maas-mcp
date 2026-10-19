"""find_available_machines: read-only sibling of acquire_machine."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._schemas.base import MachineSlim
from maasmcp.maas.client import MaasClient

# Client-side status filtering, kept deliberately: the vendored doc and
# current live MAAS accept ?status=..., but older releases have rejected it
# with 400, so these curated verbs filter on the `status_name` field.
# `status` is an integer enum (`0`/`1`/...) — `status_name` is the string
# ("New", "Ready", "Commissioned", ...).
_DEFAULT_STATUS = "Ready"
_STATUS_FIELD = "status_name"


class FindAvailableMachinesTool:
    name = "find_available_machines"
    description = (
        "Find machines that match the given status and optional filters. "
        "Use this read-only tool before acquire_machine to inspect candidates "
        "without allocating them. "
        "Returns a list of lightweight machine dicts containing system_id, "
        "hostname, status_name, power_state, tag_names, and pool. "
        "Read-only; no confirmation needed."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        hostname: Annotated[
            str | None, Field(description="Exact hostname to match (no pattern/glob support).")
        ] = None,
        pool: Annotated[str | None, Field(description="Resource pool name to filter by.")] = None,
        status: Annotated[
            str, Field(description="Machine status_name to filter by (default 'Ready').")
        ] = _DEFAULT_STATUS,
    ) -> list[MachineSlim]:
        # Paginated: on MAAS versions that paginate /machines/, the default
        # page (~50) would silently drop machines beyond page 1. Unpaginated
        # versions get the single-GET fallback in maas/paginated_get.py.
        # Cap is enforced server-side via MaasClient._max_paginated_items.
        machines: list[Any] = await client.paginated_get(
            "/api/2.0/machines/",
            paginate=True,
        )
        view: list[MachineSlim] = []
        for m in machines:
            if not isinstance(m, dict):
                continue
            if m.get(_STATUS_FIELD) != status:
                continue
            if hostname and m.get("hostname") != hostname:
                continue
            if pool and (m.get("pool") or {}).get("name") != pool:
                continue
            row: MachineSlim = {
                "system_id": m.get("system_id"),
                "hostname": m.get("hostname"),
                "status_name": m.get(_STATUS_FIELD),
                "power_state": m.get("power_state"),
                "tag_names": m.get("tag_names", []),
                "pool": (m.get("pool") or {}).get("name"),
            }
            view.append(row)
        return view
