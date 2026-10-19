"""TypedDict schemas for tag, user, and zone curated tools."""

from __future__ import annotations

from typing import Any, NotRequired

from typing_extensions import TypedDict


class Tag(TypedDict):
    """MAAS tag object returned by tags_list/tags_read/tag_read/tags_create/tag_update."""

    name: str
    comment: NotRequired[str | None]
    definition: NotRequired[str | None]
    kernel_opts: NotRequired[str | None]


class User(TypedDict):
    """MAAS user object returned by users_list/users_read/user_read/users_create."""

    id: NotRequired[int]
    username: str
    email: NotRequired[str]
    is_superuser: NotRequired[bool]
    last_name: NotRequired[str]
    first_name: NotRequired[str]


class Zone(TypedDict):
    """MAAS zone object returned by zones_list/zone_read/zones_create/zone_update."""

    id: int
    name: str
    description: NotRequired[str | None]


class BulkTagResult(TypedDict):
    """Per-machine result returned by bulk_tag_machines and bulk_untag_machines."""

    system_id: str
    status: str
    result: NotRequired[Any]
    error: NotRequired[str | None]


__all__ = [
    "BulkTagResult",
    "Tag",
    "User",
    "Zone",
]
