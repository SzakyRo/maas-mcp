"""network_layout: composite read of a machine's network topology.

Sequential Stage 1 (interfaces + subnets) followed by data-driven Stage 2
(per-fabric VLAN fan-out once Stage 1 reveals which fabrics the machine
touches). Final assembly is in-memory join.

If any Stage 1 gather raises, the verb returns partial=True plus an errors
list and a partial tree; the agent can decide whether the partial info is
sufficient or whether to retry.

VLAN URL scope note (MAAS 3.7+)
-------------------------------
MAAS VLAN endpoints are fabric-scoped:
``GET /api/2.0/fabrics/{fabric_id}/vlans/{vid}/``. We build a map from
MAAS's internal ``vlan.id`` (the primary key returned on interfaces and
embedded in subnet ``vlan: {...}``) to ``(fabric_id, vid)`` using the
subnet response from Stage 1 — every VLAN the machine touches has at
least one subnet, so this is a closed-form lookup. See
``_network_helpers`` if more elaborate translation is needed in the future.
"""

from __future__ import annotations

import asyncio
from typing import Annotated, Any, cast

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._network_paths import (
    _validate_ids,
    interfaces_path,
    subnets_path,
    vlan_path,
    vlans_path,
)
from maasmcp.curated._resolve import resolve_system_id
from maasmcp.curated._schemas.base import NetworkInterface, NetworkLayout
from maasmcp.maas.client import MaasClient


def _parse_list(resp: Any, key: str) -> list[dict[str, Any]]:
    """Accept wrapped {key: [...]} or bare-list shapes."""
    if isinstance(resp, dict) and key in resp:
        return list(resp[key])
    if isinstance(resp, list):
        return resp
    return []


def _internal_to_fabric_vid(
    subnets: list[dict[str, Any]], internal_id: int
) -> tuple[int, int] | None:
    """Translate MAAS internal VLAN primary key → (fabric_id, vid).

    Walks the subnet list looking for any subnet whose ``vlan.id``
    matches ``internal_id``. Returns the ``(fabric_id, vid)`` pair if
    the embedded ``vlan`` object has both, else ``None``. This is the
    bridge that lets us build fabric-scoped VLAN URLs from the
    interface's MAAS-internal ``vlan_id`` field.

    MAAS field-name note
    --------------------
    The embedded ``vlan`` object exposes the fabric as TWO fields:

    - ``fabric_id`` — integer fabric primary key (e.g. ``1``)
    - ``fabric``    — string fabric name      (e.g. ``"fabric-1"``)

    We must read ``fabric_id`` (integer), not ``fabric`` (string).
    Earlier versions of this helper read ``fabric`` and gated the
    return on ``isinstance(fabric_id, int)`` — that silently failed in
    production because the string name is never an int, leaving
    ``vlan_url_keys`` empty and every count at zero. Defensive: also
    accept ``fabric`` when it is unexpectedly an integer.
    """
    for s in subnets:
        if not isinstance(s, dict):
            continue
        v = s.get("vlan")
        if not isinstance(v, dict):
            continue
        if v.get("id") != internal_id:
            continue
        # Prefer fabric_id (integer); fall back to fabric only if it
        # is itself an int (defends against MAAS schema drift).
        raw_fabric = v.get("fabric_id")
        if not isinstance(raw_fabric, int):
            raw_fabric = v.get("fabric")
        vid = v.get("vid")
        if isinstance(raw_fabric, int) and isinstance(vid, int):
            return raw_fabric, vid
    return None


class NetworkLayoutTool:
    name = "network_layout"
    description = (
        "Synthesized composite read: fans out GETs for a machine's interfaces, "
        "all subnets, and per-fabric VLAN lists, then joins them in memory. "
        "Use as a read-only shortcut instead of calling list_interfaces, "
        "list_subnets, and get_vlan separately. "
        "Returns a dict with fabric_count, vlan_count, subnet_count, "
        "interface_count, ip_range_count (currently always 0), interfaces[] — "
        "where each interface's 'vlan' and 'linked_subnet' are derived "
        "heuristically from its untagged VLAN (the first subnet seen on that "
        "VLAN, not the interface's own links[] records — cross-check "
        "get_interface when exact links matter) — plus fabric_vlan_counts, a "
        "partial flag, and an errors list (partial=True means some upstream "
        "reads failed and the tree is incomplete). "
        "Accepts system_id or hostname (provide exactly one). "
        "Read-only; no confirmation needed."
    )

    async def _stage1(
        self, client: MaasClient, system_id: str, errors: list[str]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Parallel fat gather: interfaces + subnets. Failures append to errors."""
        results: list[Any] = list(
            await asyncio.gather(
                client.get(interfaces_path(system_id)),
                client.get(subnets_path()),
                return_exceptions=True,
            )
        )
        ifaces_resp, subnets_resp = results[0], results[1]
        interfaces: list[dict[str, Any]] = []
        if isinstance(ifaces_resp, BaseException):
            errors.append(f"list_interfaces: {ifaces_resp!r}")
        else:
            interfaces = _parse_list(ifaces_resp, "interfaces")
        subnets: list[dict[str, Any]] = []
        if isinstance(subnets_resp, BaseException):
            errors.append(f"list_subnets: {subnets_resp!r}")
        else:
            subnets = _parse_list(subnets_resp, "subnets")
        return interfaces, subnets

    def _resolve_touched_vlans(
        self, interfaces: list[dict[str, Any]], subnets: list[dict[str, Any]], errors: list[str]
    ) -> dict[int, tuple[int, int]]:
        """Build internal vlan_id → (fabric_id, vid) from the Stage-1 subnets.

        The interface response carries MAAS's internal vlan_id (primary key),
        but MAAS's VLAN URL needs (fabric_id, vid). Every VLAN has ≥1 subnet,
        so the Stage-1 subnet response is a closed-form lookup.
        """
        touched_vlan_ids: set[int] = set()
        for iface in interfaces:
            v = iface.get("vlan_id")
            if isinstance(v, int):
                touched_vlan_ids.add(v)
            # also catch nested vlan fields the agent may inspect
            v2 = iface.get("vlan")
            if isinstance(v2, dict) and isinstance(v2.get("id"), int):
                touched_vlan_ids.add(v2["id"])

        vlan_url_keys: dict[int, tuple[int, int]] = {}
        for internal_id in touched_vlan_ids:
            mapping = _internal_to_fabric_vid(subnets, internal_id)
            if mapping is not None:
                vlan_url_keys[internal_id] = mapping
            else:
                # The phrasing matters here: the failure mode is
                # MAAS did not return a subnet whose `vlan.id` matches
                # this internal id, NOT a transient upstream error.
                # Telling the agent to call `get_vlan(internal_id)` will
                # fail (get_vlan needs fabric_id + vid, not internal id).
                # Surface a useful next-step: list_subnets / list_vlans
                # for the fabric this VLAN lives on.
                errors.append(
                    f"vlan_resolution(internal_id={internal_id}): no subnet "
                    f"embeds this VLAN — cannot build fabric-scoped URL. "
                    f"Try list_subnets to enumerate VLANs, or list_vlans on "
                    f"each fabric (fabric_id=0..N) to discover the owning "
                    f"fabric and 802.1Q vid."
                )
        return vlan_url_keys

    async def _fetch_vlans(
        self, client: MaasClient, vlan_url_keys: dict[int, tuple[int, int]], errors: list[str]
    ) -> dict[int, dict[str, Any]]:
        """Fetch each touched VLAN; keyed back by internal id (sorted order)."""
        vlan_lookups = await asyncio.gather(
            *(
                client.get(vlan_path(fabric_id, vid))
                for (fabric_id, vid) in (
                    vlan_url_keys[internal_id] for internal_id in sorted(vlan_url_keys)
                )
            ),
            return_exceptions=True,
        )
        vlan_by_id: dict[int, dict[str, Any]] = {}
        for internal_id, resp in zip(sorted(vlan_url_keys), vlan_lookups, strict=True):
            if isinstance(resp, BaseException):
                errors.append(f"get_vlan({internal_id}): {resp!r}")
            elif isinstance(resp, dict):
                vlan_by_id[internal_id] = resp
        return vlan_by_id

    async def _fetch_fabric_vlan_counts(
        self, client: MaasClient, touched_fabric_ids: set[int], errors: list[str]
    ) -> dict[int, int]:
        """Per-fabric VLAN counts — only for fabrics the machine touches.

        Cluster-wide fetch would be wasteful and would break the
        empty-machine test (which expects partial=False).
        """
        fabric_vlan_results = await asyncio.gather(
            *(client.get(vlans_path(fid)) for fid in sorted(touched_fabric_ids)),
            return_exceptions=True,
        )
        fabric_vlan_counts: dict[int, int] = {}
        for fid, resp in zip(sorted(touched_fabric_ids), fabric_vlan_results, strict=True):
            if isinstance(resp, BaseException):
                errors.append(f"list_fabric_vlans({fid}): {resp!r}")
                fabric_vlan_counts[fid] = 0
            else:
                fabric_vlan_counts[fid] = len(_parse_list(resp, "vlans"))
        return fabric_vlan_counts

    def _touched_subnets(
        self, interfaces: list[dict[str, Any]], subnets: list[dict[str, Any]]
    ) -> tuple[dict[int, dict[str, Any]], set[int]]:
        """Subnet index + the ids of subnets on any VLAN the machine touches."""
        subnet_by_id = {s["id"]: s for s in subnets if isinstance(s, dict) and "id" in s}
        touched_subnet_ids: set[int] = set()
        for iface in interfaces:
            iface_internal_id: int | None = iface.get("vlan_id")
            if isinstance(iface_internal_id, int):
                for sid, s in subnet_by_id.items():
                    v = s.get("vlan")
                    if isinstance(v, dict) and v.get("id") == iface_internal_id:
                        touched_subnet_ids.add(sid)
                    elif s.get("vlan") == iface_internal_id:
                        # Legacy shape where vlan is a bare int (id).
                        touched_subnet_ids.add(sid)
        return subnet_by_id, touched_subnet_ids

    def _join_interfaces(
        self,
        interfaces: list[dict[str, Any]],
        vlan_by_id: dict[int, dict[str, Any]],
        subnet_by_id: dict[int, dict[str, Any]],
        touched_subnet_ids: set[int],
    ) -> list[NetworkInterface]:
        """In-memory join: interface → vlan object + linked subnet + children."""
        joined_interfaces: list[NetworkInterface] = []
        for iface in interfaces:
            v = iface.get("vlan_id")
            vlan_obj: dict[str, Any] | None = None
            if isinstance(v, int) and v in vlan_by_id:
                vl = vlan_by_id[v]
                # MAAS returns both `fabric_id` (integer) and `fabric`
                # (string name) on a top-level VLAN record — same field
                # naming as the embedded vlan object on a subnet. Prefer
                # fabric_id; fall back to fabric only if it's an int
                # (defends against MAAS schema drift).
                raw_fabric = vl.get("fabric_id")
                if not isinstance(raw_fabric, int):
                    raw_fabric = vl.get("fabric")
                vlan_obj = {
                    "id": vl.get("id", v),
                    "name": vl.get("name"),
                    "vid": vl.get("vid"),
                    "fabric_id": raw_fabric if isinstance(raw_fabric, int) else None,
                }
            linked_subnet: dict[str, Any] | None = None
            if isinstance(v, int):
                for sid in touched_subnet_ids:
                    s = subnet_by_id.get(sid, {})
                    sub_v = s.get("vlan")
                    sub_vid_matches = (isinstance(sub_v, dict) and sub_v.get("id") == v) or s.get(
                        "vlan"
                    ) == v
                    if sub_vid_matches:
                        linked_subnet = {
                            "id": s.get("id"),
                            "cidr": s.get("cidr"),
                            "gateway_ip": s.get("gateway_ip"),
                        }
                        break
            parents = iface.get("parents") or []
            joined_interfaces.append(
                cast(
                    NetworkInterface,
                    {
                        "id": iface.get("id"),
                        "name": iface.get("name"),
                        "type": iface.get("type", "unknown"),
                        "mac_address": iface.get("mac_address"),
                        "vlan": vlan_obj,
                        "linked_subnet": linked_subnet,
                        "parents": list(parents) if isinstance(parents, list) else [],
                        "children": [],  # populated below
                        "ip_addresses": list(iface.get("ip_addresses") or []),
                    },
                )
            )

        # Populate children for parent interfaces
        for child in joined_interfaces:
            for parent_id in child["parents"]:
                for parent in joined_interfaces:
                    if parent["id"] == parent_id:
                        parent["children"].append(child["id"])
        return joined_interfaces

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
    ) -> NetworkLayout:
        system_id = await resolve_system_id(client, system_id, hostname)
        _validate_ids(system_id)
        errors: list[str] = []

        interfaces, subnets = await self._stage1(client, system_id, errors)
        vlan_url_keys = self._resolve_touched_vlans(interfaces, subnets, errors)
        vlan_by_id = await self._fetch_vlans(client, vlan_url_keys, errors)

        # fabric_count is the number of distinct fabrics the machine touches
        # (via VLANs on its interfaces). Spec Section 8 explicitly scopes
        # this to "the fabrics the machine touches" — cluster-wide
        # `len(fabrics)` would over-count fabrics the machine doesn't use.
        touched_fabric_ids = {fid for fid, _vid in vlan_url_keys.values()}
        fabric_vlan_counts = await self._fetch_fabric_vlan_counts(
            client, touched_fabric_ids, errors
        )

        subnet_by_id, touched_subnet_ids = self._touched_subnets(interfaces, subnets)

        # IP ranges: count for v0.5.0 is 0 (no per-subnet IP-range fetch wired
        # yet); spec notes that explicit per-subnet list_ip_ranges may be
        # required for full info.
        ip_range_count = 0

        joined_interfaces = self._join_interfaces(
            interfaces, vlan_by_id, subnet_by_id, touched_subnet_ids
        )

        return cast(
            NetworkLayout,
            {
                "system_id": system_id,
                "fabric_count": len(touched_fabric_ids),
                "vlan_count": len(vlan_by_id),
                "subnet_count": len(touched_subnet_ids),
                "interface_count": len(joined_interfaces),
                "ip_range_count": ip_range_count,
                "interfaces": joined_interfaces,
                "partial": bool(errors),
                "errors": errors,
                "fabric_vlan_counts": fabric_vlan_counts,
            },
        )
