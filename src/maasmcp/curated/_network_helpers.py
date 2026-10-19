"""Async helpers for post-creation network link-state classification.

These helpers probe a freshly-created bond/bridge and its members, then
classify the result so callers can distinguish the normal LACP/bridge
slave-suppression pattern from real physical-layer faults.

MAAS reports ``link_connected: false`` on a physical NIC that is part of an
LACP bond or bridge, because the kernel suppresses slave carriers until the
parent aggregates. MAAS never re-probes the slave link state after
creation, so the field stays stale even when the bond is healthy.

The helpers in this module are intentionally tolerant: a probe failure
classifies the result as ``"unknown"`` rather than raising, because the
preceding ``create_*`` call already succeeded — we're annotating the
result, not re-validating it.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from maasmcp.curated._network_paths import interface_path

if TYPE_CHECKING:
    from maasmcp.maas.client import MaasClient


async def probe_link_states(
    client: MaasClient,
    system_id: str,
    parent_id: int,
    member_ids: list[int],
) -> tuple[dict[str, Any], list[str]]:
    """Fetch the parent + member interface dicts in parallel.

    Uses ``asyncio.gather(return_exceptions=True)`` so a single fetch
    failure does not poison the whole probe — same pattern as
    ``network_layout.py:60``.

    Returns:
        (link_states, errors)

        ``link_states`` is ``{"parent": dict | None, "members": list[dict]}``.
        ``parent`` is the freshly-created bond/bridge; ``members`` are the
        underlying physicals. Either can be ``None`` / empty on failure.

        ``errors`` is a list of stringified fetch failures (empty on
        full success). Useful for callers that want to log probe
        problems without surfacing them as tool failures.
    """
    urls = [interface_path(system_id, parent_id)] + [
        interface_path(system_id, mid) for mid in member_ids
    ]
    results = await asyncio.gather(
        *(client.get(url) for url in urls),
        return_exceptions=True,
    )
    errors: list[str] = []
    link_states: dict[str, Any] = {"parent": None, "members": []}

    if isinstance(results[0], BaseException):
        errors.append(f"get_interface({parent_id}): {results[0]!r}")
    elif isinstance(results[0], dict):
        link_states["parent"] = results[0]

    for i, mid in enumerate(member_ids, start=1):
        # gather preserves order and length, so results[i] always exists.
        resp = results[i]
        if isinstance(resp, BaseException):
            errors.append(f"get_interface({mid}): {resp!r}")
        elif isinstance(resp, dict):
            link_states["members"].append(resp)

    return link_states, errors


def classify_link_states(link_states: dict[str, Any]) -> str:
    """Classify the post-creation link state into one of six buckets.

    Returns one of:

    - ``bond_up_members_down`` — parent up, all members down. **Expected**
      LACP / bridge slave-suppression. No action needed.
    - ``bond_up_members_up`` — parent up, all members up. Uncommon;
      informational.
    - ``bond_up_members_mixed`` — parent up, members in mixed states.
      Review.
    - ``bond_down_members_up`` — parent down, all members up. Likely
      aggregator / switch-port misconfiguration; review.
    - ``bond_down_members_down`` — parent down, all members down.
      Physical-layer fault (cable / SFP / switch port).
    - ``bond_down_members_mixed`` — parent down, mixed member states.
      Partial configuration; review.
    - ``unknown`` — parent fetch failed (see ``errors`` list from
      ``probe_link_states``), or no members were probeable.
    """
    parent = link_states.get("parent")
    if not isinstance(parent, dict):
        return "unknown"
    parent_up = bool(parent.get("link_connected"))

    members = link_states.get("members") or []
    member_states: list[bool] = [
        bool(m.get("link_connected")) for m in members if isinstance(m, dict)
    ]
    if not member_states:
        return "unknown"

    all_up = all(member_states)
    all_down = not any(member_states)
    prefix = "bond_up" if parent_up else "bond_down"
    if all_up:
        suffix = "members_up"
    elif all_down:
        suffix = "members_down"
    else:
        suffix = "members_mixed"
    return f"{prefix}_{suffix}"
