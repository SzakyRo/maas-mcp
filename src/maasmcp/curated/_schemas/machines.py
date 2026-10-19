"""TypedDict schemas for machine lifecycle curated tools.

These describe the shapes returned by read-oriented machine tools. They are
loose (``NotRequired`` for optional fields) because MAAS may omit fields
depending on endpoint and version; runtime code still does best-effort
extraction.
"""

from __future__ import annotations

from typing import Any, NotRequired

from typing_extensions import TypedDict


class MachineRecord(TypedDict):
    """Loose MAAS machine record returned by wait_for_state and raw reads.

    The full MAAS machine dict is large and version-dependent, so this only
    captures the commonly inspected fields. Unknown fields are still present at
    runtime but are not part of the declared schema.
    """

    system_id: NotRequired[str | None]
    hostname: NotRequired[str | None]
    status: NotRequired[int]
    status_name: NotRequired[str | None]
    power_state: NotRequired[str | None]
    osystem: NotRequired[str | None]
    distro_series: NotRequired[str | None]
    architecture: NotRequired[str | None]
    memory: NotRequired[int | None]
    cpu_count: NotRequired[int | None]
    tag_names: NotRequired[list[str]]
    pool: NotRequired[dict[str, Any] | None]
    zone: NotRequired[dict[str, Any] | None]
    owner: NotRequired[str | dict[str, Any] | None]
    boot_disk: NotRequired[Any]
    commissioning_status_name: NotRequired[str | None]
    pxe_mac: NotRequired[str | None]
    ip_addresses: NotRequired[list[str]]


__all__ = ["MachineRecord"]
