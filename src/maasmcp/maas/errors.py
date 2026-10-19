"""Typed exception hierarchy for MAAS upstream interactions."""

from __future__ import annotations


class MAASError(Exception):
    """Base class for all maasmcp MAAS errors."""


class MAASAuthError(MAASError):
    """MAAS rejected the configured credentials."""


class MCPUpstreamError(MAASError):
    """MAAS upstream returned a non-retryable error after exhausting retries."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        url: str,
        detail: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.url = url
        self.detail = detail

    def __str__(self) -> str:
        # Lead with MAAS's own reason — that's what lets a user or an agent
        # fix the request. The bare "upstream 400" headline is meaningless
        # on its own, so the status only qualifies the detail, never
        # the other way around. (Synthetic errors pass status_code=0.)
        if self.detail:
            if self.status_code:
                return f"{self.detail} (upstream {self.status_code})"
            return self.detail
        return str(self.args[0])


class MCPUpstreamTimeout(MAASError):
    """MAAS upstream timed out after exhausting retries."""

    def __init__(self, message: str, *, url: str) -> None:
        super().__init__(message)
        self.url = url


class PaginationCapExceeded(MAASError):
    """Auto-pagination hit `max_items` and the underlying iterator still has more."""

    def __init__(self, message: str, *, cap: int) -> None:
        super().__init__(message)
        self.cap = cap
