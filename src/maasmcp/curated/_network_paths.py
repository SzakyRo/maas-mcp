"""Path templating helpers for networking verbs.

Single source of truth for the network URL spaces so a typo can't drift
across the 35 verbs that touch them. Per v0.5.0 spec global constraint:
no inline f-string path construction elsewhere.

The ``_validate_ids`` function lives in ``_storage_paths`` and is generic
over ID names; we re-export it here so networking verb imports stay in
one place (no cross-domain chatter at the verb layer).

VLAN path notes (MAAS 3.7+)
---------------------------
MAAS fabric-scopes every VLAN endpoint under
``/api/2.0/fabrics/{fabric_id}/vlans/...`` — see maasapi.md lines
11340-11483 for VlanHandler / VlansHandler. There is NO global
``/api/2.0/vlans/`` endpoint. The ``vid`` segment in the URL is the
IEEE 802.1Q VLAN identifier (e.g. 79), NOT the MAAS internal primary
key (e.g. 5001); the latter is keyed by the global ``id`` field but is
not used in URL construction.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from maasmcp.curated._storage_paths import _validate_id, _validate_ids

if TYPE_CHECKING:
    from maasmcp.maas.client import MaasClient

__all__ = [
    "_resolve_vlan_id",
    "_validate_id",
    "_validate_ids",
    "fabric_path",
    "fabrics_path",
    "interface_op_path",
    "interface_path",
    "interfaces_collection_op_path",
    "interfaces_path",
    "ip_range_path",
    "ip_ranges_path",
    "space_path",
    "spaces_path",
    "subnet_path",
    "subnets_path",
    "vlan_path",
    "vlans_path",
]


def fabrics_path() -> str:
    return "/api/2.0/fabrics/"


def fabric_path(fabric_id: int) -> str:
    return f"/api/2.0/fabrics/{fabric_id}/"


def spaces_path() -> str:
    return "/api/2.0/spaces/"


def space_path(space_id: int) -> str:
    return f"/api/2.0/spaces/{space_id}/"


def vlans_path(fabric_id: int) -> str:
    """List VLANs on a fabric: ``GET /api/2.0/fabrics/{fabric_id}/vlans/``.

    MAAS does not expose a global /vlans/ collection endpoint — the
    collection is always fabric-scoped.
    """
    _validate_id(fabric_id=fabric_id, _allow_zero=True)
    return f"/api/2.0/fabrics/{fabric_id}/vlans/"


def vlan_path(fabric_id: int, vid: int) -> str:
    """Item-level VLAN URL: ``/api/2.0/fabrics/{fabric_id}/vlans/{vid}/``.

    The ``vid`` segment is the IEEE 802.1Q VLAN identifier (0..4094),
    not MAAS's internal primary key; ``0`` is the fabric's built-in
    untagged default VLAN (the target of e.g. ``vlan update <fabric> 0
    primary_rack=...`` when enabling MAAS-managed DHCP). To translate a
    user-supplied internal ``id`` to ``(fabric_id, vid)``, look up the
    VLAN via :func:`_resolve_vlan_id` (via list_subnets, which embeds
    the ``vlan: {vid, id, fabric}`` shape).
    """
    _validate_id(fabric_id=fabric_id, _allow_zero=True)
    if not 0 <= vid <= 4094:
        raise ValueError(f"vlan vid must be in 0..4094 (got {vid})")
    return f"/api/2.0/fabrics/{fabric_id}/vlans/{vid}/"


def subnets_path() -> str:
    return "/api/2.0/subnets/"


def subnet_path(subnet_id: int) -> str:
    return f"/api/2.0/subnets/{subnet_id}/"


def ip_ranges_path() -> str:
    return "/api/2.0/ipranges/"


def ip_range_path(ip_range_id: int) -> str:
    return f"/api/2.0/ipranges/{ip_range_id}/"


def interfaces_path(system_id: str) -> str:
    return f"/api/2.0/nodes/{system_id}/interfaces/"


def interface_path(system_id: str, iface_id: int) -> str:
    return f"/api/2.0/nodes/{system_id}/interfaces/{iface_id}/"


def interface_op_path(system_id: str, iface_id: int, op: str) -> str:
    """Item-level interface operations (op-link_subnet, op-unlink_subnet,
    op-add_tag, op-set_default_gateway, etc.). For *creation* ops like
    op-create_bond / op-create_bridge / op-create_vlan, MAAS exposes them
    at the collection level — use ``interfaces_collection_op_path`` instead.
    """
    return f"/api/2.0/nodes/{system_id}/interfaces/{iface_id}/{op}"


def interfaces_collection_op_path(system_id: str, op: str) -> str:
    """Collection-level interface operations (op-create_bond, op-create_bridge,
    op-create_vlan). MAAS does not accept the iface_id as a path segment here."""
    return f"/api/2.0/nodes/{system_id}/interfaces/{op}"


async def _resolve_vlan_id(client: MaasClient, vid: int) -> int:
    """Translate an IEEE 802.1Q VID (e.g. 79) to MAAS's internal VLAN primary key
    (e.g. 5001). MAAS's interface PUT body requires the internal id, not the VID.

    Looks up via ``list_subnets`` since every VLAN exposed via MAAS has at least
    one subnet, and ``list_subnets`` returns the ``vlan: {vid, id}`` shape we need.
    Raises ValueError if no subnet on the given VID is visible.
    """
    subnets = await client.get(subnets_path())
    if not isinstance(subnets, list):
        raise ValueError(
            f"could not resolve VLAN id for VID {vid}: list_subnets returned "
            f"non-list {type(subnets).__name__}"
        )
    for subnet in subnets:
        if not isinstance(subnet, dict):
            continue
        vlan_obj = subnet.get("vlan")
        if isinstance(vlan_obj, dict) and vlan_obj.get("vid") == vid:
            internal_id = vlan_obj.get("id")
            if isinstance(internal_id, int):
                return internal_id
    raise ValueError(
        f"no subnet found on VLAN {vid}; cannot resolve MAAS internal id. "
        f"Create a subnet on VLAN {vid} first (create_subnet)."
    )
