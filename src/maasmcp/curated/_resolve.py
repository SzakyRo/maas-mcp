"""Shared hostname↔system_id resolution for curated verbs.

MAAS addresses machines by system_id in URL paths; hostname exists upstream
only as an exact-match list filter (GET /machines/?hostname=...). Every
machine-addressed tool accepts at least one of system_id/hostname and
resolves it to a concrete system_id. Both may be supplied together when
they agree (the resolved hostname maps back to the same system_id), so
the failure case is only "neither provided" (or a conflicting pair).
All machine-addressed verbs go
"""

from __future__ import annotations

from typing import Any

from maasmcp.maas.client import MaasClient


async def _machine_list(client: MaasClient, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Fetch the machine collection, normalizing both known response shapes.

    MAAS normally returns a bare list; some deployments wrap it as
    ``{"count": N, "results": [...]}``. Handle both.

    The no-params (fleet-map) fetch uses paginated_get so deployments that
    actually paginate /machines/ don't drop later pages; a hostname-filtered
    lookup is bounded and stays on a single GET.
    """
    if params is None:
        machines: Any = await client.paginated_get("/api/2.0/machines/", paginate=True)
    else:
        machines = await client.get("/api/2.0/machines/", params=params)
    if isinstance(machines, dict):
        machines = machines.get("results", [])
    if not isinstance(machines, list):
        raise ValueError("unexpected response listing machines")
    return machines


async def _lookup_hostname(client: MaasClient, hostname: str) -> str:
    hits = await _machine_list(client, {"hostname": hostname})
    if not hits:
        raise ValueError(f"no machine found with hostname {hostname!r}")
    # MAAS enforces unique hostnames; if a misbehaving server returns >1,
    # first-hit matches the historical tag_machine behavior.
    sid = hits[0].get("system_id")
    if not isinstance(sid, str) or not sid:
        raise ValueError(f"machine with hostname {hostname!r} has no system_id")
    return sid


async def resolve_system_id(
    client: MaasClient,
    system_id: str | None,
    hostname: str | None,
) -> str:
    """Resolve system_id/hostname arguments to a system_id.

    system_id-only is returned unverified (no extra round-trip; MAAS errors
    surface on the real call). hostname triggers one exact-match list call.
    Both set must agree, else ValueError; neither set raises immediately.
    """
    if system_id is None and hostname is None:
        raise ValueError("must provide at least one of system_id or hostname")
    if hostname is not None:
        resolved = await _lookup_hostname(client, hostname)
        if system_id is not None and resolved != system_id:
            raise ValueError(
                f"system_id {system_id!r} does not belong to hostname {hostname!r} "
                f"(it resolves to {resolved!r})"
            )
        return resolved
    assert system_id is not None
    return system_id


async def resolve_hostnames(
    client: MaasClient, hostnames: list[str]
) -> tuple[dict[str, str], list[str]]:
    """Resolve many hostnames with ONE fleet fetch + in-memory map.

    Returns (hostname→system_id map, list of unmatched hostnames). An empty
    input short-circuits without any HTTP call.
    """
    if not hostnames:
        return {}, []
    machines = await _machine_list(client)
    by_hostname = {
        m["hostname"]: m["system_id"]
        for m in machines
        if isinstance(m, dict)
        and isinstance(m.get("hostname"), str)
        and isinstance(m.get("system_id"), str)
    }
    mapping = {h: by_hostname[h] for h in hostnames if h in by_hostname}
    missing = [h for h in hostnames if h not in by_hostname]
    return mapping, missing
