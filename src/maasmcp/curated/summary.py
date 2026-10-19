"""summary: fleet-wide counts and totals."""

from __future__ import annotations

import asyncio
from collections import Counter
from typing import Annotated

from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._schemas.base import FleetSummary
from maasmcp.maas.client import MaasClient


class SummaryTool:
    name = "summary"
    description = (
        "Return a single-call fleet-wide summary of machines and pods. "
        "Use as a high-level overview before drilling down with list_machines, "
        "get_machine, or other targeted tools. "
        "Returns a dict with machine_count, pod_count, by_status, by_pool, "
        "by_zone, total_memory_mb, total_cpu_count, and pod_count_by_status. "
        "Read-only; no confirmation needed."
    )

    async def run(self, client: Annotated[MaasClient, SkipJsonSchema()]) -> FleetSummary:
        # Fetch both lists concurrently — they don't depend on each other.
        # Both endpoints paginated; without this, a fleet >50 machines or
        # >50 pods silently drops everything beyond page 1 (MAAS default
        # page size). Cap is server-side via MaasClient._max_paginated_items.
        machines_raw, pods_raw = await asyncio.gather(
            client.paginated_get("/api/2.0/machines/", paginate=True),
            client.paginated_get("/api/2.0/pods/", paginate=True),
        )
        machines_list = machines_raw if isinstance(machines_raw, list) else []
        pods_list = pods_raw if isinstance(pods_raw, list) else []

        by_status: Counter[str] = Counter()
        by_pool: Counter[str] = Counter()
        by_zone: Counter[str] = Counter()
        total_memory = 0
        total_cpu = 0
        for m in machines_list:
            if not isinstance(m, dict):
                continue
            by_status[str(m.get("status_name", "UNKNOWN"))] += 1
            pool_obj = m.get("pool") or {}
            if not isinstance(pool_obj, dict):
                pool_obj = {}
            pool_name = str(pool_obj.get("name", "unknown"))
            by_pool[pool_name] += 1
            zone_obj = m.get("zone") or {}
            if isinstance(zone_obj, dict):
                zone_name = str(zone_obj.get("name", "unknown"))
                by_zone[zone_name] += 1
            total_memory += int(m.get("memory") or 0)
            total_cpu += int(m.get("cpu_count") or 0)

        pod_count_by_status: Counter[str] = Counter()
        for p in pods_list:
            if isinstance(p, dict):
                pod_count_by_status[str(p.get("status_name", "UNKNOWN"))] += 1

        result: FleetSummary = {
            "by_status": dict(by_status),
            "by_pool": dict(by_pool),
            "by_zone": dict(by_zone),
            "total_memory_mb": total_memory,
            "total_cpu_count": total_cpu,
            "machine_count": len(machines_list),
            "pod_count": len(pods_list),
            "pod_count_by_status": dict(pod_count_by_status),
        }
        return result
