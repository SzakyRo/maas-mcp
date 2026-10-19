"""Path templating helpers for machine lifecycle verbs.

Single source of truth for the /api/2.0/machines/ URL space so a typo can't
drift across the ~20 verbs that touch it. Per spec global constraint: no
inline f-string path construction elsewhere.

Item-level MachineHandler ops appear in BOTH wire shapes, so there is one
builder per shape: path-suffix ops (POST /machines/{system_id}/op-power_on)
via :func:`machine_op_path`, and query-param ops
(POST /machines/{system_id}/?op=abort) via :func:`machine_query_op_path`.
Collection-level ops (?op=accept, ?op=set_zone) use :func:`machines_op_path`.

The ``validate_system_id`` helper lives in ``_storage_paths`` and is generic;
re-exported here so machine-verb imports stay in one place (mirrors the
``_network_paths`` re-export).
"""

from __future__ import annotations

from maasmcp.curated._storage_paths import validate_system_id

__all__ = [
    "machine_op_path",
    "machine_path",
    "machine_query_op_path",
    "machines_op_path",
    "machines_path",
    "validate_system_id",
]


def machines_path() -> str:
    return "/api/2.0/machines/"


def machines_op_path(op: str) -> str:
    """Collection-level machine operation: ``/api/2.0/machines/?op=accept``."""
    return f"{machines_path()}?op={op}"


def machine_path(system_id: str) -> str:
    """Item-level machine URL: ``/api/2.0/machines/{system_id}/``."""
    validate_system_id(system_id)
    return f"/api/2.0/machines/{system_id}/"


def machine_op_path(system_id: str, op: str) -> str:
    """Path-suffix item operation: ``/api/2.0/machines/{system_id}/op-power_on``.

    Callers pass the full op token (e.g. ``"op-release"``), mirroring the
    convention of :func:`maasmcp.curated._network_paths.interface_op_path`.
    """
    validate_system_id(system_id)
    return f"{machine_path(system_id)}{op}"


def machine_query_op_path(system_id: str, op: str) -> str:
    """Query-param item operation: ``/api/2.0/machines/{system_id}/?op=abort``.

    Callers pass the bare op name (e.g. ``"abort"``); the ``?op=`` prefix is
    added here.
    """
    validate_system_id(system_id)
    return f"{machine_path(system_id)}?op={op}"
