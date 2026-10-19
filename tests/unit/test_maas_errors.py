from __future__ import annotations

import pytest

from maasmcp.maas.errors import (
    MAASAuthError,
    MAASError,
    MCPUpstreamError,
    MCPUpstreamTimeout,
    PaginationCapExceeded,
)


def test_maas_error_is_base() -> None:
    assert issubclass(MAASAuthError, MAASError)
    assert issubclass(MCPUpstreamError, MAASError)
    assert issubclass(MCPUpstreamTimeout, MAASError)
    assert issubclass(PaginationCapExceeded, MAASError)


def test_upstream_error_carries_status_and_url() -> None:
    err = MCPUpstreamError(
        "boom", status_code=503, url="https://maas.example.com/MAAS/api/2.0/machines/"
    )
    assert err.status_code == 503
    assert err.url == "https://maas.example.com/MAAS/api/2.0/machines/"
    assert "boom" in str(err)


def test_upstream_error_carries_detail_and_stringifies_it() -> None:
    err = MCPUpstreamError(
        "upstream 400",
        status_code=400,
        url="https://maas.example.com/MAAS/api/2.0/machines/",
        detail="hostname: Already exists",
    )
    assert err.detail == "hostname: Already exists"
    # The MAAS reason leads the message; the status only qualifies it.
    assert str(err) == "hostname: Already exists (upstream 400)"


def test_upstream_error_without_status_omits_qualifier() -> None:
    # Synthetic failures (e.g. deploy_machine's commissioning gate) pass
    # status_code=0; the message must not render a bogus "upstream 0".
    err = MCPUpstreamError("commissioning failed", status_code=0, url="/x", detail="node is Broken")
    assert str(err) == "node is Broken"


def test_upstream_error_without_detail_keeps_plain_message() -> None:
    err = MCPUpstreamError(
        "upstream 404", status_code=404, url="https://maas.example.com/MAAS/api/2.0/machines/"
    )
    assert err.detail is None
    assert str(err) == "upstream 404"


def test_timeout_carries_url() -> None:
    err = MCPUpstreamTimeout("timed out", url="https://maas.example.com/MAAS/api/2.0/machines/")
    assert err.url == "https://maas.example.com/MAAS/api/2.0/machines/"


def test_pagination_cap_is_distinct() -> None:
    with pytest.raises(PaginationCapExceeded):
        raise PaginationCapExceeded("hit cap", cap=1000)
