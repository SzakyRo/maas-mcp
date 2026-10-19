"""apply_storage_layout: composite verb that sequences leaf CRUD to build
storage layouts (RAID with /boot/efi off-array, RAID without ESP, plain).

Sequential executor (no asyncio.gather — storage writes have data dependencies).
Verify-after-each-step via list_partitions / list_raids. Returns a partial-result
dict on mid-sequence failure (matches network_layout); raises only on caller-error
conditions (validation, confirm gate, NotImplementedError for reserved fields).
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._resolve import resolve_system_id
from maasmcp.curated._schemas.storage import ApplyStorageLayoutResult, CompletedStep
from maasmcp.curated._storage_paths import _validate_ids, partitions_path, raids_path
from maasmcp.curated.create_partition import CreatePartitionTool
from maasmcp.curated.create_raid import CreateRaidTool
from maasmcp.curated.format_block_device import FormatBlockDeviceTool
from maasmcp.curated.format_partition import FormatPartitionTool
from maasmcp.curated.mount_block_device import MountBlockDeviceTool
from maasmcp.curated.mount_partition import MountPartitionTool
from maasmcp.curated.set_boot_disk import SetBootDiskTool
from maasmcp.maas.client import MaasClient
from maasmcp.maas.errors import MCPUpstreamError

_SUPPORTED_LAYOUT_TYPES = frozenset({"raid_with_esp", "raid", "plain"})
_RAID_LEVELS = frozenset({0, 1, 5, 6, 10})


def _scan_partitions(disks: list[Any]) -> tuple[bool, bool]:
    """Walk all partitions once; return (esp_seen, root_seen)."""
    esp_seen = False
    root_seen = False
    for disk in disks:
        if not isinstance(disk, dict):
            raise ValueError(f"each entry in disks must be a dict, got {disk!r}")
        did = disk.get("block_device_id")
        if not isinstance(did, int) or did <= 0:
            raise ValueError(f"disk.block_device_id must be > 0, got {did!r}")
        parts = disk.get("partitions")
        if not isinstance(parts, list) or not parts:
            raise ValueError(f"disk {did}.partitions must be a non-empty list, got {parts!r}")
        for part in parts:
            if not isinstance(part, dict):
                raise ValueError(f"each partition must be a dict, got {part!r}")
            size = part.get("size")
            if size is not None and (not isinstance(size, str) or not size):
                raise ValueError(f"partition size must be a non-empty string, got {size!r}")
            # "remaining" (or omitting size) = consume the rest of the disk;
            # MAAS takes size-omitted, the sentinel is remapped before the wire.
            if size == "remaining" and any(
                p.get("size") == "remaining" for p in parts if p is not part
            ):
                raise ValueError(f"disk {did}: more than one partition claims 'remaining' space")
            if part.get("fstype") == "fat32" and part.get("mount_point") == "/boot/efi":
                esp_seen = True
            if part.get("mount_point") == "/":
                root_seen = True
    return esp_seen, root_seen


def _validate_spec(layout: Any) -> None:
    """Pre-flight spec validation. Raises ValueError on bad shape."""
    if not isinstance(layout, dict):
        raise ValueError("layout must be a dict")
    layout_type = layout.get("layout_type")
    if layout_type not in _SUPPORTED_LAYOUT_TYPES:
        raise ValueError(
            f"layout_type must be one of {sorted(_SUPPORTED_LAYOUT_TYPES)}, got {layout_type!r}"
        )
    if layout.get("volume_group"):
        raise NotImplementedError(
            "volume_group on top of RAID is not supported by this tool; "
            "omit the field or set to null/empty"
        )
    disks = layout.get("disks")
    if not isinstance(disks, list) or not disks:
        raise ValueError(f"layout.disks must be a non-empty list, got {disks!r}")
    boot_disk = layout.get("boot_disk")
    if not isinstance(boot_disk, dict):
        raise ValueError(f"layout.boot_disk must be a dict with block_device_id, got {boot_disk!r}")
    boot_disk_id = boot_disk.get("block_device_id")
    if not isinstance(boot_disk_id, int) or boot_disk_id <= 0:
        raise ValueError(f"boot_disk.block_device_id must be > 0, got {boot_disk_id!r}")
    esp_seen, root_seen = _scan_partitions(disks)
    raid = layout.get("raid")
    if layout_type.startswith("raid"):
        if not isinstance(raid, dict):
            raise ValueError(f"layout.raid must be a dict for raid layouts, got {raid!r}")
        if raid.get("level") not in _RAID_LEVELS:
            raise ValueError(
                f"raid.level must be one of {sorted(_RAID_LEVELS)}, got {raid.get('level')!r}"
            )
        if raid.get("filesystem") and raid.get("mount_point") == "/":
            root_seen = True
    if not esp_seen:
        raise ValueError(
            "layout must include one partition with fstype=fat32 and mount_point=/boot/efi"
        )
    if not root_seen:
        raise ValueError(
            "layout must mount root filesystem at / (raid.filesystem + mount_point='/' or a disk partition mount_point='/')"
        )


def _summarize_spec(spec: dict[str, Any]) -> str:
    """One-line summary used in the confirm gate error message."""
    disk_count = len(spec.get("disks", []))
    raid = spec.get("raid") or {}
    return (
        f"layout_type={spec.get('layout_type')}, "
        f"disk_count={disk_count}, "
        f"raid_level={raid.get('level')}, "
        f"boot_disk={spec.get('boot_disk', {}).get('block_device_id')}"
    )


class _Sequencer:
    """Accumulates completed steps and renders partial-failure results."""

    def __init__(self, system_id: str, layout: dict[str, Any]) -> None:
        self.system_id = system_id
        self.layout = layout
        self.completed: list[CompletedStep | dict[str, Any]] = []
        self.errors: list[str] = []

    def record(self, step: str, **fields: Any) -> None:
        entry: dict[str, Any] = {"step": step}
        entry.update(fields)
        self.completed.append(entry)

    def partial(self, failed: dict[str, Any], err: str) -> ApplyStorageLayoutResult:
        return {
            "system_id": self.system_id,
            "layout_type": self.layout.get("layout_type"),
            "status": "partial",
            "completed_steps": self.completed,
            "failed_step": failed,
            "errors": [*self.errors, err],
            "rollback_hint": (
                "To restore blank state, call op-restore_storage_configuration "
                "on the machine (raw MAAS endpoint, not exposed as a curated "
                "verb). Or call op-set_storage_layout with storage_layout=blank."
            ),
        }


class ApplyStorageLayoutTool:
    name = "apply_storage_layout"
    description = (
        "Apply a custom storage layout to a MAAS machine by sequencing "
        "partition, format, mount, RAID, and boot-disk steps. "
        "This is a composite verb that replaces calling create_partition, "
        "format_partition, mount_partition, create_raid, and set_boot_disk "
        "individually; the machine's default_storage_layout should be blank "
        "so the final layout matches the spec. Partition sizes use bytes or a "
        "single unit suffix ('100G', '500M'); the string 'remaining' (or an "
        "omitted size) on a partition makes it consume the rest of the disk — "
        "those partitions are the members picked up into a RAID. A RAID with a "
        "'filesystem' is both formatted AND mounted at 'mount_point' (the "
        "format/mount target is the RAID's virtual md device). "
        "Returns a dict with status ('complete'|'partial'), completed_steps, "
        "failed_step, errors, and rollback_hint. "
        "Accepts system_id or hostname (provide exactly one). "
        "DESTRUCTIVE — must pass confirm=True; rejected otherwise."
    )

    async def _apply_partitions(
        self, client: MaasClient, system_id: str, disks: list[Any], seq: _Sequencer
    ) -> tuple[list[int], ApplyStorageLayoutResult | None]:
        """Create/verify/format/mount every partition. Returns
        (raid_member_partition_ids, partial_result_or_None)."""
        partition_ids: list[int] = []  # RAID-member partitions, by insertion order
        for disk in disks:
            did = disk["block_device_id"]
            for part in disk["partitions"]:
                # "remaining"/omitted → size left off the POST body so MAAS
                # assigns all available space (upstream BytesField would
                # 400 on the literal sentinel or a %-string).
                raw_size = part.get("size")
                size = None if raw_size in (None, "remaining") else raw_size
                try:
                    resp = await CreatePartitionTool().run(
                        client,
                        system_id=system_id,
                        block_device_id=did,
                        size=size,
                        confirm=True,
                    )
                except (MCPUpstreamError, ValueError) as exc:
                    return [], seq.partial(
                        {
                            "step": "create_partition",
                            "params": {"disk_id": did, "size": raw_size},
                        },
                        f"create_partition(disk={did}): {exc!r}",
                    )
                pid = resp.get("id") if isinstance(resp, dict) else None
                if not isinstance(pid, int):
                    return [], seq.partial(
                        {
                            "step": "create_partition",
                            "params": {"disk_id": did, "size": raw_size},
                        },
                        f"create_partition(disk={did}) returned non-dict or no id: {resp!r}",
                    )
                seq.record("create_partition", disk_id=did, partition_id=pid)
                listed = await client.get(partitions_path(system_id, did))
                if not isinstance(listed, list) or not any(
                    isinstance(p, dict) and p.get("id") == pid for p in listed
                ):
                    return [], seq.partial(
                        {
                            "step": "verify_partition",
                            "params": {"disk_id": did, "partition_id": pid},
                        },
                        f"verify_partition(disk={did}, partition={pid}) failed; "
                        f"list_partitions did not return pid",
                    )
                if raw_size in (None, "remaining"):
                    partition_ids.append(pid)
                if part.get("fstype"):
                    try:
                        await FormatPartitionTool().run(
                            client,
                            system_id=system_id,
                            block_device_id=did,
                            partition_id=pid,
                            fstype=part["fstype"],
                            confirm=True,
                        )
                    except (MCPUpstreamError, ValueError) as exc:
                        return [], seq.partial(
                            {
                                "step": "format_partition",
                                "params": {"partition_id": pid, "fstype": part["fstype"]},
                            },
                            f"format_partition(partition={pid}): {exc!r}",
                        )
                    seq.record("format_partition", partition_id=pid, fstype=part["fstype"])
                if part.get("mount_point"):
                    try:
                        await MountPartitionTool().run(
                            client,
                            system_id=system_id,
                            block_device_id=did,
                            partition_id=pid,
                            mount_point=part["mount_point"],
                            confirm=True,
                        )
                    except (MCPUpstreamError, ValueError) as exc:
                        return [], seq.partial(
                            {
                                "step": "mount_partition",
                                "params": {"partition_id": pid, "mount_point": part["mount_point"]},
                            },
                            f"mount_partition(partition={pid}): {exc!r}",
                        )
                    seq.record("mount_partition", partition_id=pid, mount_point=part["mount_point"])
        return partition_ids, None

    async def _apply_raid(
        self,
        client: MaasClient,
        system_id: str,
        raid: dict[str, Any],
        partition_ids: list[int],
        seq: _Sequencer,
    ) -> ApplyStorageLayoutResult | None:
        """Create/verify/format the RAID over ``partition_ids``.
        Returns a partial-result dict on failure, None on success."""
        try:
            raid_resp = await CreateRaidTool().run(
                client,
                system_id=system_id,
                level=raid["level"],
                name=raid.get("name"),
                partitions=partition_ids,
                confirm=True,
            )
        except (MCPUpstreamError, ValueError) as exc:
            return seq.partial(
                {"step": "create_raid", "params": {"level": raid["level"]}},
                f"create_raid(level={raid['level']}): {exc!r}",
            )
        raid_id = raid_resp.get("id") if isinstance(raid_resp, dict) else None
        if not isinstance(raid_id, int):
            return seq.partial(
                {"step": "create_raid", "params": {"level": raid["level"]}},
                f"create_raid returned non-dict or no id: {raid_resp!r}",
            )
        seq.record("create_raid", raid_id=raid_id, level=raid["level"])
        listed_raids = await client.get(raids_path(system_id))
        if not isinstance(listed_raids, list) or not any(
            isinstance(r, dict) and r.get("id") == raid_id for r in listed_raids
        ):
            return seq.partial(
                {"step": "verify_raid", "params": {"raid_id": raid_id}},
                f"verify_raid(raid_id={raid_id}) failed; list_raids did not return raid_id",
            )
        if raid.get("filesystem"):
            # format/mount operate on the RAID's virtual block device
            # (md device id), not on the filesystem-group (raid) id —
            # those live in different namespaces.
            vdev = raid_resp.get("virtual_device") if isinstance(raid_resp, dict) else None
            vdev_id = vdev.get("id") if isinstance(vdev, dict) else None
            if not isinstance(vdev_id, int):
                return seq.partial(
                    {"step": "create_raid", "params": {"level": raid["level"]}},
                    f"create_raid response lacked virtual_device.id: {raid_resp!r}",
                )
            try:
                await FormatBlockDeviceTool().run(
                    client,
                    system_id=system_id,
                    block_device_id=vdev_id,
                    fstype=raid["filesystem"],
                    confirm=True,
                )
            except (MCPUpstreamError, ValueError) as exc:
                return seq.partial(
                    {
                        "step": "format_raid",
                        "params": {"vdev_id": vdev_id, "fstype": raid["filesystem"]},
                    },
                    f"format_raid(vdev={vdev_id}): {exc!r}",
                )
            seq.record("format_raid", block_device_id=vdev_id, fstype=raid["filesystem"])
            if raid.get("mount_point"):
                try:
                    await MountBlockDeviceTool().run(
                        client,
                        system_id=system_id,
                        block_device_id=vdev_id,
                        mount_point=raid["mount_point"],
                        confirm=True,
                    )
                except (MCPUpstreamError, ValueError) as exc:
                    return seq.partial(
                        {
                            "step": "mount_raid",
                            "params": {
                                "vdev_id": vdev_id,
                                "mount_point": raid["mount_point"],
                            },
                        },
                        f"mount_raid(vdev={vdev_id}): {exc!r}",
                    )
                seq.record("mount_raid", block_device_id=vdev_id, mount_point=raid["mount_point"])
        return None

    async def _apply_boot_disk(
        self, client: MaasClient, system_id: str, boot_disk_id: int, seq: _Sequencer
    ) -> ApplyStorageLayoutResult | None:
        """Set the boot disk. Returns a partial-result dict on failure."""
        try:
            await SetBootDiskTool().run(
                client,
                system_id=system_id,
                block_device_id=boot_disk_id,
                confirm=True,
            )
        except (MCPUpstreamError, ValueError) as exc:
            return seq.partial(
                {
                    "step": "set_boot_disk",
                    "params": {"block_device_id": boot_disk_id},
                },
                f"set_boot_disk: {exc!r}",
            )
        seq.record("set_boot_disk", block_device_id=boot_disk_id)
        return None

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
        layout: Annotated[
            dict[str, Any] | None,
            Field(
                description="Storage layout spec dict describing disks, partitions, optional RAID, and boot_disk."
            ),
        ] = None,
        *,
        hostname: Annotated[
            str | None,
            Field(description="Exact hostname of the machine; resolved to system_id server-side."),
        ] = None,
        confirm: Annotated[
            bool, Field(description="Must be True to proceed. This operation is destructive.")
        ] = False,
    ) -> ApplyStorageLayoutResult:
        # Fail fast on a missing layout before the hostname resolution
        # round-trip — avoids a wasted GET /machines/?hostname=... on an
        # error path.
        if layout is None:
            raise ValueError("layout is required")
        system_id = await resolve_system_id(client, system_id, hostname)
        _validate_ids(system_id)
        _validate_spec(layout)
        if confirm is not True:
            raise ValueError(
                "apply_storage_layout is destructive; pass confirm=True. "
                f"Affected: system_id={system_id}, hostname={hostname}, spec={_summarize_spec(layout)}"
            )

        seq = _Sequencer(system_id, layout)

        partition_ids, failed = await self._apply_partitions(
            client, system_id, layout["disks"], seq
        )
        if failed is not None:
            return failed

        if layout["layout_type"].startswith("raid"):
            failed = await self._apply_raid(client, system_id, layout["raid"], partition_ids, seq)
            if failed is not None:
                return failed

        failed = await self._apply_boot_disk(
            client, system_id, layout["boot_disk"]["block_device_id"], seq
        )
        if failed is not None:
            return failed

        return {
            "system_id": system_id,
            "layout_type": layout["layout_type"],
            "status": "complete",
            "completed_steps": seq.completed,
            "failed_step": None,
            "errors": [],
            "rollback_hint": "",
        }
