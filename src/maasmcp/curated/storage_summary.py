"""storage_summary: sequential Stage 1 (devices), fat Stage 2 (partitions + raids + VGs)."""

from __future__ import annotations

import asyncio
from typing import Annotated, Any

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._resolve import resolve_system_id
from maasmcp.curated._schemas.base import StorageSummary
from maasmcp.curated._storage_paths import (
    _validate_ids,
    block_devices_path,
    partitions_path,
    raids_path,
    volume_groups_path,
)
from maasmcp.maas.client import MaasClient


def _to_gib(size_bytes: int) -> float:
    """Convert bytes (MAAS may return as int or string) to GiB."""
    try:
        n = int(size_bytes)
    except (TypeError, ValueError):
        return 0.0
    return round(n / (1024**3), 2)


def _parse_block_devices(resp: Any) -> list[dict[str, Any]]:
    """Accept wrapped {"blockdevices": [...]} or bare-list shapes."""
    if isinstance(resp, dict) and "blockdevices" in resp:
        return list(resp["blockdevices"])
    if isinstance(resp, list):
        return resp
    return []


def _parse_raids(resp: Any) -> list[dict[str, Any]]:
    """Accept wrapped {"raids": [...]} or bare-list shapes."""
    if isinstance(resp, dict) and "raids" in resp:
        return list(resp["raids"])
    if isinstance(resp, list):
        return resp
    return []


def _parse_volume_groups(resp: Any) -> list[dict[str, Any]]:
    """Accept wrapped {"volume_groups": [...]} or bare-list shapes."""
    if isinstance(resp, dict) and "volume_groups" in resp:
        return list(resp["volume_groups"])
    if isinstance(resp, list):
        return resp
    return []


def _count_lvs_in_vg(vg: dict[str, Any]) -> int:
    """Best-effort extraction of LV count from a VG dict.

    Tries ``logical_volumes`` first (MAAS docs terminology at
    maasapi.md:12311), then ``volumes``. Returns 0 on neither match
    (the agent still sees correct RAID/VG counts).
    """
    for key in ("logical_volumes", "volumes"):
        member = vg.get(key)
        if isinstance(member, list):
            return len(member)
    return 0


class StorageSummaryTool:
    name = "storage_summary"
    description = (
        "Return a cross-resource summary of a machine's storage layout. "
        "Use as a read-only shortcut instead of calling list_block_devices, "
        "list_partitions, list_raids, and list_volume_groups separately. "
        "Returns a dict with system_id, block_devices, partitions, total_size_gib, "
        "raid_devices, volume_groups, and logical_volumes. "
        "Partition counting is best-effort: MAAS's /partitions/ endpoint 500s on "
        "whole-disk raid-member devices, and those devices are skipped rather "
        "than failing the summary. "
        "Accepts system_id or hostname (provide exactly one). "
        "Read-only; no confirmation needed."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        system_id: Annotated[
            str | None,
            Field(
                description="MAAS system_id of the machine. "
                "Provide this or hostname, exactly one."
            ),
        ] = None,
        *,
        hostname: Annotated[
            str | None,
            Field(description="Exact hostname of the machine; resolved to system_id server-side."),
        ] = None,
    ) -> StorageSummary:
        system_id = await resolve_system_id(client, system_id, hostname)
        _validate_ids(system_id)

        # Stage 1: block devices (sequential — sizes Stage 2 partition fan-out)
        devices_resp = await client.get(block_devices_path(system_id))
        devices = _parse_block_devices(devices_resp)

        # Stage 2: per-device partitions + raids + volume-groups in parallel
        *partition_lists, raids_resp, vgs_resp = await asyncio.gather(
            *(client.get(partitions_path(system_id, d["id"])) for d in devices),
            client.get(raids_path(system_id)),
            client.get(volume_groups_path(system_id)),
            return_exceptions=True,
        )

        partitions = 0
        for pl in partition_lists:
            if isinstance(pl, Exception):
                continue
            if isinstance(pl, dict) and "partitions" in pl:
                partitions += len(pl["partitions"])
            elif isinstance(pl, list):
                partitions += len(pl)

        raids = _parse_raids(raids_resp)
        vgs = _parse_volume_groups(vgs_resp)
        logical_volumes = sum(_count_lvs_in_vg(vg) for vg in vgs)
        total_gib = sum(_to_gib(d.get("size", 0)) for d in devices)

        return {
            "system_id": system_id,
            "block_devices": len(devices),
            "partitions": partitions,
            "total_size_gib": total_gib,
            "raid_devices": len(raids),
            "volume_groups": len(vgs),
            "logical_volumes": logical_volumes,
        }
