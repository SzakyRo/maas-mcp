"""clear_boot_disk: attempt to unpin a machine's boot_disk.

MAAS does NOT expose a clear/unset boot_disk verb — `set_boot_disk` is the
only documented BlockDeviceHandler operation, and `MachineHandler.update`
(PUT /api/2.0/machines/{id}/) 405s on a boot_disk field. Confirmed against
MAAS 3.7.2 OpenAPI spec (docs/reference/maasapi.md §BlockDeviceHandler_set_boot_disk) and
live testing: `{"boot_disk": null}` and `{"boot_disk": 0}` both 405.

Rather than fake a call, this tool surfaces the limitation as structured
data and lists the available workarounds, so the gap is discoverable via
MCP rather than via failed raw-API probes.

Design choices:
- confirm-gated even though no destructive action is performed here — the
  caller is explicitly asking the MCP to "try to clear," so the gate
  matches the intent. The dry-run path returns the current state without
  the workarounds array, useful for pre-checks.
- Workarounds are listed in increasing destructive order, so the agent can
  pick the cheapest viable option without re-querying.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._machine_paths import machine_path, validate_system_id
from maasmcp.curated._resolve import resolve_system_id
from maasmcp.curated._schemas.storage import ClearBootDiskResult, CurrentBootDisk
from maasmcp.maas.client import MaasClient


class ClearBootDiskTool:
    name = "clear_boot_disk"
    description = (
        "Attempt to clear a MAAS machine's boot disk pin and return the "
        "current state plus available workarounds. "
        "Use this to discover that MAAS has no clear/unset boot_disk verb "
        "before probing the raw API; if the pin is genuinely wrong, choose "
        "from the returned workarounds (release+redeploy or delete+re-enlist). "
        "Returns a dict with status ('noop'|'unsupported'), system_id, reason, "
        "current_boot_disk, and available_workarounds. "
        "Accepts system_id or hostname (provide exactly one). "
        "Confirm-gated; must pass confirm=True (no destructive action is "
        "performed, but the gate matches the caller's intent)."
    )

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
        confirm: Annotated[
            bool,
            Field(
                description="Must be True to proceed. No destructive action is performed, but the gate matches the caller's intent."
            ),
        ] = False,
    ) -> ClearBootDiskResult:
        system_id = await resolve_system_id(client, system_id, hostname)
        validate_system_id(system_id)
        if not system_id:
            raise ValueError("system_id must be a non-empty string")
        if confirm is not True:
            raise ValueError(
                "clear_boot_disk is confirm-gated even though it cannot "
                "actually clear the pin (MAAS has no clear verb). Pass "
                "confirm=True to receive the current state and the list of "
                "available workarounds. "
                f"Affected: system_id={system_id}, hostname={hostname}"
            )

        # Fetch current state via the same path get_machine uses. MAAS returns
        # boot_disk as an embedded block-device dict on the singular endpoint.
        machine: Any = await client.get(machine_path(system_id))
        if not isinstance(machine, dict):
            raise ValueError(
                f"unexpected response for machine {system_id!r}: got {type(machine).__name__}"
            )

        raw_boot_disk = machine.get("boot_disk")
        current: CurrentBootDisk
        if isinstance(raw_boot_disk, dict):
            current = {
                "boot_disk_id": raw_boot_disk.get("id"),
                "boot_disk_name": raw_boot_disk.get("name"),
                "boot_disk_path": raw_boot_disk.get("path") or raw_boot_disk.get("id_path"),
            }
        elif isinstance(raw_boot_disk, int):
            current = {
                "boot_disk_id": raw_boot_disk,
                "boot_disk_name": None,
                "boot_disk_path": None,
            }
        else:
            current = {
                "boot_disk_id": None,
                "boot_disk_name": None,
                "boot_disk_path": None,
            }

        already_unpinned = current["boot_disk_id"] is None
        return {
            "status": "noop" if already_unpinned else "unsupported",
            "system_id": system_id,
            "operation": "clear_boot_disk",
            "reason": (
                "no boot disk is currently pinned; nothing to clear"
                if already_unpinned
                else (
                    "MAAS does not expose a clear/unset boot_disk verb. "
                    "The only documented operation is BlockDeviceHandler_set_boot_disk "
                    "(POST /api/2.0/nodes/{system_id}/blockdevices/{id}/op-set_boot_disk), "
                    "and MachineHandler.update (PUT /api/2.0/machines/{system_id}/) "
                    "rejects the boot_disk field with HTTP 405. There is no "
                    "documented path to unpin."
                )
            ),
            "current_boot_disk": current,
            "available_workarounds": (
                []
                if already_unpinned
                else [
                    {
                        "name": "release_and_redeploy",
                        "destructive": True,
                        "description": (
                            "release_machine (with erase=true) then deploy_machine. "
                            "The new deployment re-runs commissioning which re-pins "
                            "the natural boot disk (first physical, SSD, smallest). "
                            "Use this if you genuinely want the pin to follow the "
                            "machine into a fresh OS."
                        ),
                        "verbs": ["release_machine", "deploy_machine"],
                    },
                    {
                        "name": "leave_pinned",
                        "destructive": False,
                        "description": (
                            "Accept that boot_disk stays pinned to the current "
                            "device. On a typical server sda is the natural boot "
                            "disk; a stale pin here is informational, not a fault. "
                            "The kernel/GRUB on the deployed OS controls actual "
                            "boot order regardless."
                        ),
                        "verbs": [],
                    },
                    {
                        "name": "delete_and_reenlist",
                        "destructive": True,
                        "description": (
                            "machine_delete then re-enlist via commissioning. "
                            "Drops the machine's entire history (tags, comments, "
                            "events). Only use if the pin is genuinely wrong and "
                            "release+redeploy is not an option."
                        ),
                        "verbs": ["machine_delete"],
                    },
                ]
            ),
        }
