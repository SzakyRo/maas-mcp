"""Hand-written MCP tools — the entire exposed MAAS surface.

Each tool is a small class (``name``, ``description``, ``run``, ``register``)
in its own module; :func:`register_curated` wires them all onto the shared
:class:`~mcp.server.mcpserver.MCPServer` instance built in :mod:`maasmcp.registry`.

Naming convention
-----------------

The ~85 modules here fall into three groups. The grouping mirrors MAAS's
own REST shape, where singular noun = per-resource endpoint keyed by id
and plural noun = collection endpoint, and keeps curated tool names
aligned with the verbs an agent would naturally write.

1. **Composite workflows** (verb-first singular). They orchestrate
   multiple MAAS calls, or wrap a single MAAS call with extra semantics
   (confirm-gate, fan-out, paginated read, etc.):

   ``acquire_machine``, ``release_machine``, ``deploy_machine``,
   ``find_available_machines``, ``apply_storage_layout``, ``set_boot_disk``,
   ``wait_for_state``, ``summary``, ``tools_index``, ``storage_summary``,
   ``network_layout``.

   These live in the first import block of :mod:`maasmcp.curated._common`.

2. **1:1 MAAS endpoint wrappers, per-resource** (singular noun). Each
   maps to a single MAAS endpoint keyed by an id in the path:

   ``machine_*``, ``block_device_*``, ``partition_*``, ``raid_*``,
   ``volume_group_*``, ``fabric_*``, ``vlan_*``, ``subnet_*``,
   ``ip_range_*``, ``interface_*``, ``space_*``, ``user_*``.

   Example: ``machine_power_parameters`` →
   ``GET /machines/{system_id}/?op=power_parameters``.

3. **1:1 MAAS endpoint wrappers, collection** (plural noun). Each maps to
   a single MAAS endpoint over the whole collection:

   ``machines_*``, ``block_devices_*``, ``partitions_*``, ``raids_*``,
   ``volume_groups_*``, ``fabrics_*``, ``vlans_*``, ``subnets_*``,
   ``ip_ranges_*``, ``interfaces_*``, ``spaces_*``, ``users_*``,
   ``zones_*``, ``tags_*``, ``ip_addresses_*``, ``ipranges_*``.

   Example: ``machines_power_parameters`` →
   ``GET /machines/?op=power_parameters&id=...``.

   Direct 1:1 MAAS endpoint imports are flagged by the comment in
   :mod:`maasmcp.curated._common` ("Direct 1:1 MAAS API tools … Exact
   names preserved for client compat.").

When you add a tool, follow the split that matches the MAAS endpoint
shape — don't reach for one of the names if the MAAS endpoint is the
other. Register the tool in :mod:`maasmcp.curated._common` (for
import-time wiring) and in :mod:`maasmcp.curated._catalog` (for the
domain / annotations / schemas map that the rebind layer consults).
"""

from maasmcp.curated._common import register_curated

__all__ = ["register_curated"]
