"""acquire_machine: find an idle machine matching constraints and allocate it."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.maas.client import MaasClient

# Client-side status filtering on `status_name`, kept deliberately (some MAAS
# releases rejected ?status=) — see find_available_machines for the rationale.
# `status` is an integer enum; `status_name` is the Title-case string.
_DEFAULT_STATUS = "Ready"
_STATUS_FIELD = "status_name"


class AcquireMachineTool:
    """Find an idle machine and allocate it. Non-idempotent."""

    name = "acquire_machine"
    description = (
        "Find an idle machine matching the given constraints and allocate it "
        "via MAAS. "
        "Use this instead of find_available_machines when you need to reserve "
        "a machine rather than only list candidates. "
        "Returns a dict with system_id, hostname, and status_name. "
        "Allocates a machine (takes it out of the Ready pool) — must pass "
        "confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        hostname: Annotated[
            str | None, Field(description="Exact hostname to match (no pattern/glob support).")
        ] = None,
        pool: Annotated[str | None, Field(description="Machine pool name to match.")] = None,
        status: Annotated[
            str, Field(description="Status name to filter by (default 'Ready').")
        ] = _DEFAULT_STATUS,
        confirm: Annotated[
            bool,
            Field(
                description="Must be True to proceed. Allocation removes the "
                "machine from the shared Ready pool."
            ),
        ] = False,
    ) -> dict[str, Any]:
        if confirm is not True:
            raise ValueError(
                "acquire_machine allocates (reserves) a machine; pass "
                "confirm=True to proceed. Constraints: "
                f"hostname={hostname!r} pool={pool!r} status={status!r}"
            )
        # No server-side status filter — see module docstring.
        # paginate=True: on MAAS versions that paginate /machines/, the
        # default page (~50) would silently drop machines beyond page 1,
        # causing a spurious no-match or a wrong-machine allocation on
        # large fleets. On unpaginated versions the pagination layer falls
        # back to a full-list GET — see maas/paginated_get.py.
        machines = await client.paginated_get("/api/2.0/machines/", paginate=True)
        # Defensive client-side filters on the real MAAS response shape.
        matches: list[dict[str, Any]] = []
        for m in machines:
            if not isinstance(m, dict):
                continue
            if m.get(_STATUS_FIELD) != status:
                continue
            if hostname and m.get("hostname") != hostname:
                continue
            if pool and (m.get("pool") or {}).get("name") != pool:
                continue
            matches.append(m)
        if not matches:
            raise ValueError(
                f"no machine matches constraints: status={status!r} "
                f"hostname={hostname!r} pool={pool!r}"
            )
        chosen = matches[0]
        # system_id alone pins the target; the allocate op's hostname param is
        # named `name` upstream, and passing a stray `hostname` key risks a 400.
        body: dict[str, Any] = {"system_id": chosen["system_id"]}
        if pool:
            body["pool"] = pool
        await client.post("/api/2.0/machines/?op=allocate", json=body)
        return {
            "system_id": chosen.get("system_id"),
            "hostname": chosen.get("hostname"),
            "status_name": chosen.get(_STATUS_FIELD),
        }
