"""release_machine: deallocate a machine; erase its disks by default (erase=true)."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._machine_paths import machine_op_path, validate_system_id
from maasmcp.curated._resolve import resolve_system_id
from maasmcp.maas.client import MaasClient


class ReleaseMachineTool:
    name = "release_machine"
    description = (
        "Release (deallocate) a machine back to the MAAS pool, erasing its "
        "disks by default (erase=true performs a full null-byte overwrite). "
        "Use only when the machine is no longer needed; call get_machine or "
        "list_machines to confirm the target first. For MAAS's firmware-level "
        "secure erase or a quick erase, use secure_erase / quick_erase. "
        "Returns the MAAS release response dict. "
        "Accepts system_id or hostname (provide exactly one). "
        "DESTRUCTIVE — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        comment: Annotated[
            str | None,
            Field(description="Optional comment recorded with the release action."),
        ] = None,
        erase: Annotated[
            bool,
            Field(
                description="If True (default), erase disks during release "
                "(full null-byte overwrite of every disk)."
            ),
        ] = True,
        secure_erase: Annotated[
            bool | None,
            Field(
                description="Use the drive's secure erase (firmware-level) when "
                "erasing. Only meaningful with erase=True; requires supported disks."
            ),
        ] = None,
        quick_erase: Annotated[
            bool | None,
            Field(
                description="Skip full-disk overwrite (fast, not a secure wipe). "
                "Only meaningful with erase=True."
            ),
        ] = None,
        force: Annotated[
            bool,
            Field(
                description="Force release even if the machine is in a non-releasable state "
                "(e.g. a deployed KVM host — the host and all machines inside it are deleted)."
            ),
        ] = False,
        *,
        system_id: Annotated[
            str | None,
            Field(
                description="MAAS system_id of the machine. "
                "Provide this or hostname, exactly one."
            ),
        ] = None,
        hostname: Annotated[
            str | None,
            Field(description="Exact hostname of the machine; resolved to system_id server-side."),
        ] = None,
        confirm: Annotated[
            bool,
            Field(description="Must be True to proceed. This operation is destructive."),
        ] = False,
    ) -> dict[str, Any] | None:
        system_id = await resolve_system_id(client, system_id, hostname)
        validate_system_id(system_id)
        if confirm is not True:
            raise ValueError(
                "release_machine is destructive (erases disks by "
                "default); pass confirm=True to proceed. "
                f"Affected: system_id={system_id}, hostname={hostname}, erase={erase}"
            )
        body: dict[str, Any] = {"erase": erase}
        if comment:
            body["comment"] = comment
        if secure_erase is not None:
            body["secure_erase"] = secure_erase
        if quick_erase is not None:
            body["quick_erase"] = quick_erase
        if force:
            body["force"] = force
        return await client.post(  # type: ignore[no-any-return]
            machine_op_path(system_id, "op-release"), json=body
        )
