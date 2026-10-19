"""Path templating helpers for storage verbs.

Single source of truth for /nodes/{system_id}/blockdevices/... paths so a
typo can't drift across the 10 verbs that touch this URL space. Per v0.3.0
spec global constraint: no inline f-string path construction elsewhere.
"""

from __future__ import annotations

import re
import urllib.parse

# MAAS system_ids are short alphanumeric host keys; restricting to RFC 3986
# unreserved characters blocks path traversal (`..`, `/`) and query
# smuggling (`?`, `#`, `%2f`) through interpolated path segments.
_SYSTEM_ID_RE = re.compile(r"^[A-Za-z0-9._~-]{1,64}$")


def validate_system_id(system_id: str) -> None:
    """Reject a system_id that isn't a safe single URL path segment."""
    if not _SYSTEM_ID_RE.match(system_id):
        raise ValueError(
            "system_id must be 1-64 chars of [A-Za-z0-9._~-] "
            f"(a single safe URL path segment), got {system_id!r}"
        )


def quote_segment(value: str) -> str:
    """Percent-encode a user-supplied value for safe URL path interpolation.

    Use for free-form identifiers whose exact charset rules belong to the
    upstream (MAAS tag names, usernames) rather than to us: encoding with
    ``safe=""`` turns ``..``, ``/``, ``?``, ``#``, ``%`` into inert bytes,
    so the value can never reshape the request path or smuggle a query.
    MAAS decodes percent-encoded path segments back to the original name.
    """
    if not value:
        raise ValueError("path segment value must be a non-empty string")
    return urllib.parse.quote(value, safe="")


def block_devices_path(system_id: str) -> str:
    return f"/api/2.0/nodes/{system_id}/blockdevices/"


def block_device_path(system_id: str, block_device_id: int) -> str:
    return f"/api/2.0/nodes/{system_id}/blockdevices/{block_device_id}/"


def partitions_path(system_id: str, block_device_id: int) -> str:
    return f"/api/2.0/nodes/{system_id}/blockdevices/{block_device_id}/partitions/"


def partition_path(system_id: str, block_device_id: int, partition_id: int) -> str:
    return f"/api/2.0/nodes/{system_id}/blockdevices/{block_device_id}/partitions/{partition_id}"


def set_boot_disk_path(system_id: str, block_device_id: int) -> str:
    return f"/api/2.0/nodes/{system_id}/blockdevices/{block_device_id}/op-set_boot_disk"


def format_block_device_path(system_id: str, block_device_id: int) -> str:
    return f"/api/2.0/nodes/{system_id}/blockdevices/{block_device_id}/op-format"


def mount_block_device_path(system_id: str, block_device_id: int) -> str:
    return f"/api/2.0/nodes/{system_id}/blockdevices/{block_device_id}/op-mount"


def unmount_block_device_path(system_id: str, block_device_id: int) -> str:
    return f"/api/2.0/nodes/{system_id}/blockdevices/{block_device_id}/op-unmount"


def format_partition_path(system_id: str, block_device_id: int, partition_id: int) -> str:
    # MAAS partition-scoped ops use a ?op=<name> query parameter, not a path
    # suffix. The literal URL in maasapi.md §PartitionHandler_format is
    # misleading on this point — see memory maas-partition-ops-query-param.
    return f"/api/2.0/nodes/{system_id}/blockdevices/{block_device_id}/partitions/{partition_id}"


def mount_partition_path(system_id: str, block_device_id: int, partition_id: int) -> str:
    return f"/api/2.0/nodes/{system_id}/blockdevices/{block_device_id}/partitions/{partition_id}"


def unmount_partition_path(system_id: str, block_device_id: int, partition_id: int) -> str:
    return f"/api/2.0/nodes/{system_id}/blockdevices/{block_device_id}/partitions/{partition_id}"


def _validate_ids(system_id: str, **ids: int) -> None:
    """Validate MAAS path parameters used by storage verbs.

    system_id: MAAS node system_id (non-empty string).
    **ids: name → positive-integer pairs (e.g. block_device_id, partition_id).

    Raises ValueError on the first invalid argument. The error message for
    each id matches the verbatim format previously inlined in each verb so
    existing tests asserting on substrings (e.g. "block_device_id") keep
    passing without modification.
    """
    validate_system_id(system_id)
    for name, value in ids.items():
        if value <= 0:
            raise ValueError(f"{name} must be > 0, got {value}")


def raids_path(system_id: str) -> str:
    return f"/api/2.0/nodes/{system_id}/raids/"


def raid_path(system_id: str, raid_id: int) -> str:
    return f"/api/2.0/nodes/{system_id}/raid/{raid_id}/"


def volume_groups_path(system_id: str) -> str:
    return f"/api/2.0/nodes/{system_id}/volume-groups/"


def volume_group_path(system_id: str, vg_id: int) -> str:
    return f"/api/2.0/nodes/{system_id}/volume-group/{vg_id}/"


def lv_create_path(system_id: str, vg_id: int) -> str:
    return f"/api/2.0/nodes/{system_id}/volume-group/{vg_id}/op-create_logical_volume"


def lv_delete_path(system_id: str, vg_id: int) -> str:
    return f"/api/2.0/nodes/{system_id}/volume-group/{vg_id}/op-delete_logical_volume"


def _validate_id(_allow_zero: bool = False, **ids: int) -> None:
    """Validate MAAS path IDs for non-machine-scoped verbs.

    For Fabric/Space/VLAN/Subnet/IP Range endpoints which don't take a
    system_id, use this in place of ``_validate_ids``. Same error format.
    ``_allow_zero=True`` is for fabric ids — MAAS fabric numbering starts at
    0 (``fabric-0`` is the default fabric), unlike other resource ids.
    """
    for name, value in ids.items():
        floor = 0 if _allow_zero else 1
        if value < floor:
            raise ValueError(f"{name} must be >= {floor}, got {value}")
