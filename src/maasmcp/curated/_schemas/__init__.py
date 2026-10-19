"""TypedDict schemas for curated tool return types.

Domain-specific schemas live in sibling modules (e.g. ``machines.py``,
``storage.py``). ``base`` contains the common shapes used across domains.
"""

from __future__ import annotations

from maasmcp.curated._schemas.base import (
    FleetSummary,
    LinkedSubnet,
    MachineNormalized,
    MachineSlim,
    NetworkInterface,
    NetworkLayout,
    StorageSummary,
    VlanRef,
)

__all__ = [
    "FleetSummary",
    "LinkedSubnet",
    "MachineNormalized",
    "MachineSlim",
    "NetworkInterface",
    "NetworkLayout",
    "StorageSummary",
    "VlanRef",
]
