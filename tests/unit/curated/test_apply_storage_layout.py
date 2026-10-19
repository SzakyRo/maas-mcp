"""apply_storage_layout: composite verb that sequences leaf CRUD to build
storage layouts (RAID with /boot/efi off-array, RAID without ESP, plain).
"""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from maasmcp.curated.apply_storage_layout import ApplyStorageLayoutTool, _validate_spec
from maasmcp.maas.client import MaasClient

_VALID_RAID_WITH_ESP = {
    "layout_type": "raid_with_esp",
    "disks": [
        {
            "block_device_id": 1,
            "partitions": [
                {"size": "1G", "fstype": "fat32", "mount_point": "/boot/efi"},
                {"size": "remaining"},
            ],
        },
        {
            "block_device_id": 2,
            "partitions": [
                {"size": "1G", "fstype": "fat32"},
                {"size": "remaining"},
            ],
        },
    ],
    "raid": {"level": 1, "name": "md0", "filesystem": "ext4", "mount_point": "/"},
    "boot_disk": {"block_device_id": 1},
}


@pytest.mark.asyncio
async def test_missing_disks_raises(maas_client: MaasClient) -> None:
    """Spec validation runs BEFORE confirm gate."""
    with respx.mock(base_url=maas_client.base_url) as mock:
        async with maas_client:
            with pytest.raises(ValueError, match="disks"):
                await ApplyStorageLayoutTool().run(
                    maas_client,
                    system_id="abc",
                    layout={
                        "layout_type": "raid_with_esp",
                        "raid": {},
                        "boot_disk": {"block_device_id": 1},
                    },
                    confirm=True,
                )
    assert not mock.calls


_VALID_PLAIN_WITH_PARTITION_ROOT = {
    "layout_type": "plain",
    "disks": [
        {
            "block_device_id": 1,
            "partitions": [
                {"size": "512M", "fstype": "fat32", "mount_point": "/boot/efi"},
                {"size": "remaining", "fstype": "ext4", "mount_point": "/"},
            ],
        },
    ],
    "boot_disk": {"block_device_id": 1},
}


def test_plain_layout_with_partition_root_passes_validation() -> None:
    """Plain layout with a partition mounted at '/' must validate without error.

    Regression: prior to this fix, _validate_spec only set root_seen=True
    inside the raid-with-filesystem branch, making layout_type='plain'
    unreachable through the public API even when a partition mounted '/'.
    """
    _validate_spec(_VALID_PLAIN_WITH_PARTITION_ROOT)


@pytest.mark.asyncio
async def test_missing_boot_disk_raises(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:
        async with maas_client:
            with pytest.raises(ValueError, match="boot_disk"):
                await ApplyStorageLayoutTool().run(
                    maas_client,
                    system_id="abc",
                    layout={
                        "layout_type": "raid_with_esp",
                        "disks": [{"block_device_id": 1, "partitions": []}],
                        "raid": {"level": 1},
                    },
                    confirm=True,
                )
    assert not mock.calls


@pytest.mark.asyncio
async def test_unknown_layout_type_raises(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:
        async with maas_client:
            with pytest.raises(ValueError, match="layout_type"):
                await ApplyStorageLayoutTool().run(
                    maas_client,
                    system_id="abc",
                    layout={
                        "layout_type": "bogus",
                        "disks": [{"block_device_id": 1, "partitions": [{"size": "1G"}]}],
                        "raid": {"level": 1},
                        "boot_disk": {"block_device_id": 1},
                    },
                    confirm=True,
                )
    assert not mock.calls


@pytest.mark.asyncio
async def test_volume_group_raises_not_implemented(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:
        async with maas_client:
            with pytest.raises(NotImplementedError, match="volume_group"):
                await ApplyStorageLayoutTool().run(
                    maas_client,
                    system_id="abc",
                    layout={**_VALID_RAID_WITH_ESP, "volume_group": {"name": "vg0"}},
                    confirm=True,
                )
    assert not mock.calls


@pytest.mark.asyncio
async def test_empty_system_id_raises_before_confirm(maas_client: MaasClient) -> None:
    """Path validation runs BEFORE confirm gate."""
    with respx.mock(base_url=maas_client.base_url) as mock:
        async with maas_client:
            with pytest.raises(ValueError, match="system_id"):
                await ApplyStorageLayoutTool().run(
                    maas_client,
                    system_id="",
                    layout=_VALID_RAID_WITH_ESP,
                    confirm=True,
                )
    assert not mock.calls


@pytest.mark.asyncio
async def test_confirm_false_is_noop(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:
        async with maas_client:
            with pytest.raises(ValueError, match="confirm=True"):
                await ApplyStorageLayoutTool().run(
                    maas_client,
                    system_id="abc",
                    layout=_VALID_RAID_WITH_ESP,
                    confirm=False,
                )
    assert not mock.calls


@pytest.mark.asyncio
async def test_happy_path_raid_with_esp(maas_client: MaasClient) -> None:
    """Full RAID 1 with ESP off-array: 2 disks x 2 partitions, format/mount,
    create_raid, format_raid + mount on the virtual md device, set_boot_disk.
    Every step verified."""
    with respx.mock(base_url=maas_client.base_url) as mock:
        pid_counter = iter([10, 11, 12, 13])
        for did in (1, 2):
            mock.post(f"/api/2.0/nodes/abc/blockdevices/{did}/partitions/").mock(
                side_effect=[
                    Response(200, json={"id": next(pid_counter)}),
                    Response(200, json={"id": next(pid_counter)}),
                ]
            )
        mock.get("/api/2.0/nodes/abc/blockdevices/1/partitions/").mock(
            return_value=Response(200, json=[{"id": 10}, {"id": 11}])
        )
        mock.get("/api/2.0/nodes/abc/blockdevices/2/partitions/").mock(
            return_value=Response(200, json=[{"id": 12}, {"id": 13}])
        )
        mock.post("/api/2.0/nodes/abc/blockdevices/1/partitions/10?op=format").mock(
            return_value=Response(200, json={})
        )
        mock.post("/api/2.0/nodes/abc/blockdevices/2/partitions/12?op=format").mock(
            return_value=Response(200, json={})
        )
        mock.post("/api/2.0/nodes/abc/blockdevices/1/partitions/10?op=mount").mock(
            return_value=Response(200, json={})
        )
        mock.post("/api/2.0/nodes/abc/raids/").mock(
            return_value=Response(200, json={"id": 99, "virtual_device": {"id": 50, "name": "md0"}})
        )
        mock.get("/api/2.0/nodes/abc/raids/").mock(return_value=Response(200, json=[{"id": 99}]))
        mock.post("/api/2.0/nodes/abc/blockdevices/50/op-format").mock(
            return_value=Response(200, json={})
        )
        mock.post("/api/2.0/nodes/abc/blockdevices/50/op-mount").mock(
            return_value=Response(200, json={})
        )
        mock.post("/api/2.0/nodes/abc/blockdevices/1/op-set_boot_disk").mock(
            return_value=Response(200, json={})
        )
        async with maas_client:
            result = await ApplyStorageLayoutTool().run(
                maas_client,
                system_id="abc",
                layout=_VALID_RAID_WITH_ESP,
                confirm=True,
            )
    assert result["status"] == "complete"
    assert result["system_id"] == "abc"
    assert result["layout_type"] == "raid_with_esp"
    assert result["errors"] == []
    step_names = [s["step"] for s in result["completed_steps"]]
    # The implementation interleaves create/format/mount per-partition,
    # not the grouped order assumed in the brief.
    assert step_names == [
        "create_partition",  # disk 1, ESP partition (id=10)
        "format_partition",  # ESP fat32
        "mount_partition",  # ESP /boot/efi
        "create_partition",  # disk 1, remaining (id=11, RAID member)
        "create_partition",  # disk 2, ESP partition (id=12)
        "format_partition",  # ESP fat32
        "create_partition",  # disk 2, remaining (id=13, RAID member)
        "create_raid",
        "format_raid",  # on the virtual md device (id=50)
        "mount_raid",  # at '/' per the spec
        "set_boot_disk",
    ]


@pytest.mark.asyncio
async def test_partial_failure_on_create_partition(maas_client: MaasClient) -> None:
    """If create_partition fails mid-sequence, return partial dict with what
    succeeded, the failed step, and the error."""
    with respx.mock(base_url=maas_client.base_url) as mock:
        mock.post("/api/2.0/nodes/abc/blockdevices/1/partitions/").mock(
            side_effect=[
                Response(200, json={"id": 10}),
                Response(409, text="disk full"),
            ]
        )
        mock.get("/api/2.0/nodes/abc/blockdevices/1/partitions/").mock(
            return_value=Response(200, json=[{"id": 10}])
        )
        mock.post("/api/2.0/nodes/abc/blockdevices/1/partitions/10?op=format").mock(
            return_value=Response(200, json={})
        )
        mock.post("/api/2.0/nodes/abc/blockdevices/1/partitions/10?op=mount").mock(
            return_value=Response(200, json={})
        )
        async with maas_client:
            result = await ApplyStorageLayoutTool().run(
                maas_client,
                system_id="abc",
                layout=_VALID_RAID_WITH_ESP,
                confirm=True,
            )
        # Capture inside mock context — mock.routes resets on exit.
        routes_snapshot = list(mock.routes)
    assert result["status"] == "partial"
    assert len(result["completed_steps"]) == 3
    assert result["completed_steps"][0]["step"] == "create_partition"
    assert result["completed_steps"][0]["partition_id"] == 10
    assert result["failed_step"] is not None
    assert result["failed_step"]["step"] == "create_partition"
    assert len(result["errors"]) >= 1
    assert "rollback" not in result["rollback_hint"].lower()
    assert "restore blank state" in result["rollback_hint"].lower()
    raid_routes = [r for r in routes_snapshot if "/raids/" in str(r.pattern)]
    assert all(r.call_count == 0 for r in raid_routes)


@pytest.mark.asyncio
async def test_verification_failure_returns_partial(maas_client: MaasClient) -> None:
    """create_partition returns 200 with id=10, but list_partitions doesn't
    show it (e.g. async visibility delay). Treat as mid-sequence failure."""
    with respx.mock(base_url=maas_client.base_url) as mock:
        mock.post("/api/2.0/nodes/abc/blockdevices/1/partitions/").mock(
            return_value=Response(200, json={"id": 10})
        )
        mock.get("/api/2.0/nodes/abc/blockdevices/1/partitions/").mock(
            return_value=Response(200, json=[])
        )
        async with maas_client:
            result = await ApplyStorageLayoutTool().run(
                maas_client,
                system_id="abc",
                layout=_VALID_RAID_WITH_ESP,
                confirm=True,
            )
    assert result["status"] == "partial"
    assert result["failed_step"]["step"] == "verify_partition"


@pytest.mark.asyncio
async def test_upstream_error_body_strip(maas_client: MaasClient) -> None:
    """MCPUpstreamError body-strip preserved: errors list shows repr but the
    underlying error's str() carries the status code only."""
    with respx.mock(base_url=maas_client.base_url) as mock:
        mock.post("/api/2.0/nodes/abc/blockdevices/1/partitions/").mock(
            return_value=Response(409, text="DISK_FULL_SECRET")
        )
        async with maas_client:
            result = await ApplyStorageLayoutTool().run(
                maas_client,
                system_id="abc",
                layout=_VALID_RAID_WITH_ESP,
                confirm=True,
            )
    assert result["status"] == "partial"
    assert "409" in str(result["errors"])
    assert "DISK_FULL_SECRET" not in str(result["errors"])


@pytest.mark.asyncio
async def test_sequencing_is_strictly_sequential(maas_client: MaasClient) -> None:
    """No asyncio.gather: each leaf is called exactly the expected number of times.
    Counts: 4 create_partition, 2 format_partition (ESPs), 1 mount_partition
    (boot/efi), 1 create_raid, 1 format_raid, 1 set_boot_disk."""
    with respx.mock(base_url=maas_client.base_url) as mock:
        pid_counter = iter([10, 11, 12, 13])
        for did in (1, 2):
            mock.post(f"/api/2.0/nodes/abc/blockdevices/{did}/partitions/").mock(
                side_effect=[
                    Response(200, json={"id": next(pid_counter)}),
                    Response(200, json={"id": next(pid_counter)}),
                ]
            )
        mock.get("/api/2.0/nodes/abc/blockdevices/1/partitions/").mock(
            return_value=Response(200, json=[{"id": 10}, {"id": 11}])
        )
        mock.get("/api/2.0/nodes/abc/blockdevices/2/partitions/").mock(
            return_value=Response(200, json=[{"id": 12}, {"id": 13}])
        )
        mock.post("/api/2.0/nodes/abc/blockdevices/1/partitions/10?op=format").mock(
            return_value=Response(200, json={})
        )
        mock.post("/api/2.0/nodes/abc/blockdevices/2/partitions/12?op=format").mock(
            return_value=Response(200, json={})
        )
        mock.post("/api/2.0/nodes/abc/blockdevices/1/partitions/10?op=mount").mock(
            return_value=Response(200, json={})
        )
        mock.post("/api/2.0/nodes/abc/raids/").mock(
            return_value=Response(200, json={"id": 99, "virtual_device": {"id": 50, "name": "md0"}})
        )
        mock.get("/api/2.0/nodes/abc/raids/").mock(return_value=Response(200, json=[{"id": 99}]))
        mock.post("/api/2.0/nodes/abc/blockdevices/50/op-format").mock(
            return_value=Response(200, json={})
        )
        mock.post("/api/2.0/nodes/abc/blockdevices/50/op-mount").mock(
            return_value=Response(200, json={})
        )
        mock.post("/api/2.0/nodes/abc/blockdevices/1/op-set_boot_disk").mock(
            return_value=Response(200, json={})
        )
        async with maas_client:
            await ApplyStorageLayoutTool().run(
                maas_client,
                system_id="abc",
                layout=_VALID_RAID_WITH_ESP,
                confirm=True,
            )
        # Capture inside mock context — mock.routes / mock.calls reset on exit.
        # Filter on mock.calls (which carry request.method) instead of
        # mock.routes (which only carry pattern repr).
        calls_snapshot = list(mock.calls)
    post_part_creates = [
        c
        for c in calls_snapshot
        if c.request.method == "POST"
        and "/partitions/" in str(c.request.url.path)
        and "op=" not in str(c.request.url)
    ]
    assert len(post_part_creates) == 4
    # Partition-scoped ops (?op=format, ?op=mount) live in the query string;
    # block-device ops (/op-format, /op-set_boot_disk) live in the path.
    # Count all format-style calls together.
    post_format = [
        c
        for c in calls_snapshot
        if c.request.method == "POST"
        and ("op=format" in str(c.request.url) or "/op-format" in str(c.request.url.path))
    ]
    assert len(post_format) == 3
    post_mount = [
        c for c in calls_snapshot if c.request.method == "POST" and "op=mount" in str(c.request.url)
    ]
    assert len(post_mount) == 1
    post_boot = [
        c
        for c in calls_snapshot
        if c.request.method == "POST" and "/op-set_boot_disk" in str(c.request.url.path)
    ]
    assert len(post_boot) == 1
    post_raid_create = [
        c
        for c in calls_snapshot
        if c.request.method == "POST" and str(c.request.url.path).endswith("/raids/")
    ]
    assert len(post_raid_create) == 1


@pytest.mark.asyncio
async def test_missing_layout_raises_before_hostname_lookup(maas_client: MaasClient) -> None:
    """layout=None must short-circuit BEFORE the hostname→system_id GET, so a
    caller passing layout=None + hostname=X never burns a round-trip to MAAS."""
    with respx.mock(base_url=maas_client.base_url, assert_all_called=False) as mock:
        route = mock.get("/api/2.0/machines/", params={"hostname": "node-x"}).mock(
            return_value=Response(200, json=[])
        )
        async with maas_client:
            with pytest.raises(ValueError, match="layout is required"):
                await ApplyStorageLayoutTool().run(
                    maas_client, hostname="node-x", layout=None, confirm=False
                )
    assert route.call_count == 0
