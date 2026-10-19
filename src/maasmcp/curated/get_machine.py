"""get_machine: lookup by system_id OR hostname, normalized view."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._machine_paths import machine_path, machines_path, validate_system_id
from maasmcp.curated._schemas.base import MachineNormalized
from maasmcp.maas.client import MaasClient
from maasmcp.maas.errors import MCPUpstreamError


class GetMachineTool:
    name = "get_machine"
    description = (
        "Fetch a single machine by either system_id or hostname. "
        "Use this as the primary lookup for one machine; if you only know the "
        "hostname, call this instead of list_machines. "
        "Returns a normalized dict: system_id, hostname, tag_names, pool, owner, "
        "power_state, os, last_commissioned, boot_disk_id, boot_disk_name. "
        "Read-only; no confirmation needed."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        identifier: Annotated[str, Field(description="MAAS system_id or hostname of the machine.")],
    ) -> MachineNormalized:
        # identifier doubles as system_id or hostname; hostnames fit the same
        # safe-segment charset ([A-Za-z0-9._~-]), so one check covers both
        # direct-fetch branches below against path traversal/query smuggling.
        validate_system_id(identifier)
        machine: Any = None
        # If it looks like a system_id (hex-ish), fetch directly — but fall
        # back to the hostname-filtered list when MAAS 404s, because an
        # all-hex hostname of length >= 6 (e.g. 'decaf0') would otherwise be
        # misclassified as a system_id. Non-hex identifiers (e.g. '84t4pa',
        # 'busy-feline') go hostname-first, then system_id, because MAAS
        # system_ids are base-36 — a valid one may contain any letter.
        if all(c in "0123456789abcdef" for c in identifier.lower()) and len(identifier) >= 6:
            try:
                machine = await client.get(machine_path(identifier))
            except MCPUpstreamError as exc:
                if exc.status_code != 404:
                    raise
        if machine is None:
            machines: Any = await client.get(machines_path(), params={"hostname": identifier})
            if not isinstance(machines, list) or not machines:
                # Last resort: maybe it IS a (non-hex) system_id.
                try:
                    machine = await client.get(machine_path(identifier))
                except MCPUpstreamError as exc:
                    if exc.status_code != 404:
                        raise
                    raise ValueError(
                        f"no machine found with hostname or system_id {identifier!r}"
                    ) from exc
            else:
                machine = machines[0]
        if not isinstance(machine, dict):
            raise ValueError(f"unexpected response for machine {identifier}")
        pool_obj = machine.get("pool") or {}
        owner_obj = machine.get("owner") or {}
        # MAAS returns boot_disk either as an embedded block-device dict
        # (GET /machines/{id}/ with default include) or as a scalar id
        # (some paginated paths). Normalize both to (id, name).
        raw_boot_disk = machine.get("boot_disk")
        if isinstance(raw_boot_disk, dict):
            boot_disk_id = raw_boot_disk.get("id")
            boot_disk_name = raw_boot_disk.get("name")
        elif isinstance(raw_boot_disk, int):
            boot_disk_id = raw_boot_disk
            boot_disk_name = None
        else:
            boot_disk_id = None
            boot_disk_name = None
        result: MachineNormalized = {
            "system_id": machine.get("system_id"),
            "hostname": machine.get("hostname"),
            "tag_names": machine.get("tag_names", []),
            "pool": pool_obj.get("name") if isinstance(pool_obj, dict) else None,
            "owner": owner_obj.get("username") if isinstance(owner_obj, dict) else None,
            "power_state": machine.get("power_state"),
            "os": ((machine.get("osystem") or "") + " " + (machine.get("distro_series") or "")).strip(),
            "last_commissioned": machine.get("last_commissioned"),
            "boot_disk_id": boot_disk_id,
            "boot_disk_name": boot_disk_name,
        }
        return result
