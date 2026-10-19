"""MAAS client package."""

from maasmcp.maas.client import MaasClient
from maasmcp.maas.errors import (
    MAASAuthError,
    MAASError,
    MCPUpstreamError,
    MCPUpstreamTimeout,
    PaginationCapExceeded,
)

__all__ = [
    "MAASAuthError",
    "MAASError",
    "MCPUpstreamError",
    "MCPUpstreamTimeout",
    "MaasClient",
    "PaginationCapExceeded",
]
