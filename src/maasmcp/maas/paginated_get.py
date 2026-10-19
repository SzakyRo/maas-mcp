"""Paginated GET helper for MAAS list endpoints.

Walks ``?limit=&offset=`` pages until a short page is returned or
``max_items`` is reached. Used by :meth:`MaasClient.paginated_get`.

MAAS support for collection pagination is version- and endpoint-dependent:
some deployments (e.g. ``/machines/`` on older releases) reject the
``limit``/``offset`` constraints outright with 400. The first page's 400
falls back to a single unpaginated GET, so fleet lists work on both kinds
of MAAS.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from maasmcp.maas.errors import MCPUpstreamError

if TYPE_CHECKING:
    from maasmcp.maas.client import MaasClient

# Default page size for each upstream request. MAAS supports much larger
# limits, but 200 keeps response bodies modest and is well within the
# documented range.
_DEFAULT_LIMIT = 200


async def paginate_get(
    client: MaasClient,
    path: str,
    params: dict[str, Any] | None,
    *,
    max_items: int,
) -> AsyncIterator[Any]:
    """Yield items from a paginated MAAS list endpoint up to ``max_items``.

    Each request adds ``limit`` and ``offset`` to ``params``. The iterator
    stops when the upstream returns a short page or ``max_items`` items
    have been yielded. Endpoints that ignore ``offset`` (echoing the same
    page back) are detected by content and stop the walk without
    duplicating items.
    """
    if max_items <= 0:
        return
    limit = _DEFAULT_LIMIT
    offset = 0
    yielded = 0
    prev_page: list[Any] | None = None
    while yielded < max_items:
        requested = min(limit, max_items - yielded)
        page_params: dict[str, Any] = dict(params or {})
        page_params["limit"] = str(requested)
        page_params["offset"] = str(offset)
        try:
            page = await client.get(path, params=page_params)
        except MCPUpstreamError as exc:
            # This MAAS version doesn't paginate this collection at all —
            # its constraint validator replies 400 {"limit": ["No such
            # constraint."], "offset": ["No such constraint."]} for e.g.
            # /machines/, while other versions (and other endpoints, e.g.
            # /pods/) do paginate. Detectable only at runtime, so: on the
            # FIRST page's 400, retry once without the pagination params.
            # An unpaginated MAAS returns the full list. If the 400 was
            # really about the caller's other params, the retry 400s as well
            # and the error surfaces unchanged.
            if offset != 0 or exc.status_code != 400:
                raise
            page = await client.get(path, params=params)
            if not isinstance(page, list):
                raise ValueError(f"expected list from {path}, got {type(page).__name__}") from exc
            for item in page:
                if yielded >= max_items:
                    return
                yielded += 1
                yield item
            return
        if not isinstance(page, list):
            raise ValueError(f"expected list from {path}, got {type(page).__name__}")
        if not page:
            return
        if offset > 0 and page == prev_page:
            # The endpoint ignored our offset and echoed the previous page —
            # walking further would only emit duplicates.
            return
        for item in page:
            if yielded >= max_items:
                return
            yielded += 1
            yield item
        # Short page (compare against the size we actually asked for, not the
        # nominal limit) — that was the last page.
        if len(page) < requested:
            return
        prev_page = page
        offset += len(page)


__all__ = ["paginate_get"]
