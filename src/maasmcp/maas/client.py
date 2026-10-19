"""Async HTTP client for the MAAS REST API."""

from __future__ import annotations

import asyncio
import html
import json
import re
import secrets
import time
import urllib.parse
import uuid
from typing import Any

import httpx
import structlog

from maasmcp.config import MaasConfig, MaasmcpConfig
from maasmcp.maas.errors import MAASAuthError, MCPUpstreamError, MCPUpstreamTimeout
from maasmcp.maas.paginated_get import paginate_get

log = structlog.get_logger(__name__)

_RETRY_DELAYS_S = (0.25, 1.0, 4.0)
_MAX_ATTEMPTS = 4  # 1 initial + 3 retries

_DEFAULT_MAX_PAGINATED_ITEMS = 1000

# Safe truncation length for upstream HTML/text error bodies.
_MAX_ERROR_DETAIL_LEN = 200

# Structured JSON keys MAAS uses for error messages. Only these are echoed
# so arbitrary JSON payloads (which may contain PII) are not leaked.
_STRUCTURED_ERROR_KEYS = ("__error__", "error", "detail", "message")

# Tokens that indicate a transient auth/session failure on a 403 response.
# We match phrases rather than bare words so a generic "Permission denied"
# or "Invalid token format" does not trigger a write retry.
_SESSION_ERROR_TOKENS = frozenset(("session expired", "token expired", "csrf"))

# Field-level validation envelopes (e.g. Django/DRF-style {"field": ["msg"]})
# are echoed only when the field name looks safe and is not credential-like.
_SAFE_FIELD_NAME_RE = re.compile(r"[a-z_][a-z0-9_]{0,63}$")
_SENSITIVE_FIELD_NAMES = frozenset(
    (
        "api_key",
        "consumer_key",
        "consumer_secret",
        "token",
        "token_key",
        "token_secret",
        "password",
        "secret",
    )
)


def _stringify(value: Any) -> str:
    """Coerce a Python scalar into a MAAS text-form multipart part.

    MAAS requires all multipart/form-data parts to be plain text. Booleans
    must render as 'true'/'false' (Python str(True) is 'True', which MAAS rejects).
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _build_multipart_body(fields: dict[str, Any]) -> tuple[bytes, str]:
    """Build a multipart/form-data body with one text part per (name, value).

    List values produce **repeated parts with the same name** — MAAS expects
    this for repeated keys (e.g. ``parents=2&parents=3``, not a stringified
    ``"[2, 3]"``). Booleans render as 'true'/'false'.

    Returns ``(body_bytes, content_type_header)``. The boundary used to
    delimit parts is encoded into the Content-Type header so the MAAS
    upstream can decode the body.
    """
    boundary = f"----maasmcp{uuid.uuid4().hex}"
    parts: list[bytes] = []
    for name, value in fields.items():
        # Field names come from our code, but guard anyway: a CR/LF in a
        # name would let it smuggle extra form parts verbatim. Field *values*
        # are user input and may legitimately contain CR/LF — they're safe
        # because the boundary carries 122 bits of per-request randomness an
        # attacker cannot predict, so keep it random: NEVER replace it with
        # a fixed string.
        if "\r" in name or "\n" in name:
            raise ValueError(f"multipart field name contains CR/LF: {name!r}")
        if isinstance(value, list):
            for v in value:
                parts.extend(
                    [
                        f"--{boundary}".encode(),
                        f'Content-Disposition: form-data; name="{name}"'.encode(),
                        b"",
                        _stringify(v).encode(),
                    ]
                )
        else:
            parts.extend(
                [
                    f"--{boundary}".encode(),
                    f'Content-Disposition: form-data; name="{name}"'.encode(),
                    b"",
                    _stringify(value).encode(),
                ]
            )
    parts.append(f"--{boundary}--".encode())
    body = b"\r\n".join(parts) + b"\r\n"
    content_type = f"multipart/form-data; boundary={boundary}"
    return body, content_type


def _is_retryable_auth_error(status_code: int, detail: str | None) -> bool:
    """Return True when the error looks like a transient auth/session failure.

    401 is always retryable: MAAS rejected the request before it reached the
    application, so replaying cannot create duplicate resources. 403 is only
    retryable when the body mentions a session/CSRF/token expiry phrase.
    """
    if status_code == 401:
        return True
    if status_code != 403 or not detail:
        return False
    lower = detail.lower()
    return any(token in lower for token in _SESSION_ERROR_TOKENS)


# MAAS surfaces Django ORM DoesNotExist lookups as bare 500s (e.g.
# "PartitionTable matching query does not exist" for a disk with no
# partition table). Those responses are deterministic — retrying the same
# request will get the same 500 — so skip the backoff loop entirely.
_DETERMINISTIC_500_TOKENS = ("matching query does not exist",)


def _is_deterministic_500(detail: str | None) -> bool:
    if not detail:
        return False
    lower = detail.lower()
    return any(token in lower for token in _DETERMINISTIC_500_TOKENS)


def _echo_field_errors(payload: dict[str, Any]) -> str | None:
    """Render Django-style {"field": ["msg"]} validation errors.

    Only safe, non-credential field names are echoed; anything credential-like
    or unusual-looking is dropped rather than surfaced.
    """
    parts: list[str] = []
    for field, messages in payload.items():
        if not isinstance(field, str):
            continue
        if field.lower() in _SENSITIVE_FIELD_NAMES:
            continue
        if not _SAFE_FIELD_NAME_RE.match(field):
            continue
        if isinstance(messages, list):
            parts.extend(f"{field}: {msg}" for msg in messages if isinstance(msg, str))
    if not parts:
        return None
    return _truncate_detail("; ".join(parts))


def _parse_upstream_error_message(response: httpx.Response) -> str | None:
    """Extract an actionable but safe message from a MAAS error response.

    Recognized JSON shapes are surfaced; arbitrary JSON payloads, which may
    contain user-provided values, are not. HTML tags are stripped and the
    resulting text is truncated.
    """
    if not response.content:
        return None

    ctype = response.headers.get("content-type", "").lower()
    text = response.text
    if not text:
        return None

    # JSON: only trust known top-level keys.
    if "json" in ctype:
        try:
            payload = response.json()
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            for key in _STRUCTURED_ERROR_KEYS:
                value = payload.get(key)
                if isinstance(value, str):
                    return _truncate_detail(value)
            if payload:
                echoed = _echo_field_errors(payload)
                if echoed is not None:
                    return echoed
        return None

    # HTML: strip tags and collapse whitespace.
    if "html" in ctype or text.lstrip().startswith("<"):
        stripped = re.sub(r"<[^>]+>", " ", text)
        stripped = html.unescape(stripped)
        stripped = re.sub(r"\s+", " ", stripped).strip()
        return _truncate_detail(stripped) if stripped else None

    # Plain text.
    return _truncate_detail(text)


def _truncate_detail(text: str) -> str:
    text = text.strip()
    if len(text) <= _MAX_ERROR_DETAIL_LEN:
        return text
    return text[: _MAX_ERROR_DETAIL_LEN - 3].rstrip() + "..."


class MaasClient:
    """Async context-managed MAAS HTTP client.

    Auth modes (selected by which MaasConfig fields are populated):
    - api_key:  Authorization: Bearer <api_key>
    - oauth:    OAuth1 signed Authorization header

    May be constructed with either a :class:`MaasConfig` (legacy, defaults
    ``max_paginated_items`` to 1000) or a :class:`MaasmcpConfig` (uses the
    configured ``server.max_paginated_items``).
    """

    def __init__(
        self,
        cfg: MaasConfig | MaasmcpConfig,
        *,
        timeout_seconds: int = 60,
    ) -> None:
        if isinstance(cfg, MaasmcpConfig):
            self._cfg = cfg.maas
            self._max_paginated_items = cfg.server.max_paginated_items
        else:
            self._cfg = cfg
            self._max_paginated_items = _DEFAULT_MAX_PAGINATED_ITEMS
        self._timeout = timeout_seconds
        self._client: httpx.AsyncClient | None = None
        self._auth_mode = self._resolve_auth_mode(self._cfg)

    @property
    def max_paginated_items(self) -> int:
        return self._max_paginated_items

    @staticmethod
    def _resolve_auth_mode(cfg: MaasConfig) -> str:
        # OAuth with a populated consumer_secret, OR OAuth PLAINTEXT with
        # an empty consumer_secret (MAAS's three-part API key shape).
        has_oauth = bool(cfg.consumer_key) and bool(cfg.token_key) and bool(cfg.token_secret)
        has_api = bool(cfg.api_key)
        if has_oauth and has_api:
            raise MAASAuthError("MaasConfig has both api_key and oauth credentials; pick one")
        if has_oauth:
            return "oauth"
        if has_api:
            return "api_key"
        raise MAASAuthError("MaasConfig has neither api_key nor full oauth credentials")

    async def __aenter__(self) -> MaasClient:
        if urllib.parse.urlparse(self._cfg.base_url).scheme == "http":
            # OAuth PLAINTEXT / Bearer credentials travel in the Authorization
            # header — over plain HTTP they are readable by any on-path party.
            log.warning(
                "maas_insecure_base_url",
                base_url=self._cfg.base_url,
                hint="MAAS credentials are sent in cleartext; use https://",
            )
        self._client = httpx.AsyncClient(
            base_url=self._cfg.base_url,
            timeout=self._timeout,
            verify=self._cfg.verify_tls,
        )
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # -- public verbs -------------------------------------------------------

    async def get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> Any:
        return await self._request("GET", path, params=params, timeout=timeout)

    async def post(
        self,
        path: str,
        json: dict[str, Any] | None = None,
        *,
        params: dict[str, Any] | None = None,
    ) -> Any:
        return await self._request("POST", path, params=params, json_body=json)

    async def put(
        self,
        path: str,
        json: dict[str, Any] | None = None,
        *,
        params: dict[str, Any] | None = None,
    ) -> Any:
        return await self._request("PUT", path, params=params, json_body=json)

    async def delete(self, path: str) -> Any:
        return await self._request("DELETE", path)

    async def paginated_get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        paginate: bool = False,
    ) -> Any:
        """GET with optional auto-pagination.

        When ``paginate`` is False (default) returns a single page response
        of any type. When True, returns a list of items aggregated across
        ``?limit=&offset=`` pages, capped at ``self.max_paginated_items``.
        """
        if not paginate:
            return await self.get(path, params=params)
        items: list[Any] = []
        async for item in paginate_get(self, path, params, max_items=self._max_paginated_items):
            items.append(item)
        return items

    # -- internals ----------------------------------------------------------

    def _require_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("MaasClient used outside `async with`")
        return self._client

    async def _send(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None,
        json_body: dict[str, Any] | None,
        timeout: float | None = None,
    ) -> httpx.Response:
        """Send one request attempt; the caller owns the retry policy.

        ``timeout`` overrides the client default for this one request —
        used by health probes that must answer faster than the (up to
        5-minute) tool-call budget.
        """
        client = self._require_client()
        headers = self._auth_headers(method, path, params=params, body=json_body)
        # MAAS requires multipart/form-data for POST/PUT bodies — each
        # part is a text key/value. httpx's `data=` kwarg with a dict
        # sends application/x-www-form-urlencoded, which MAAS rejects
        # with 400. Build the multipart body bytes manually.
        # An empty dict is normalized to no body at all: MAAS 400s on a
        # bodyless-content-type request (see set_boot_disk), so callers may
        # pass {} freely without constructing the failure themselves.
        body_bytes: bytes | None = None
        if json_body and method in {"POST", "PUT"}:
            body_bytes, ctype = _build_multipart_body(json_body)
            headers = {**headers, "Content-Type": ctype}
        request_kwargs: dict[str, Any] = {}
        if timeout is not None:
            request_kwargs["timeout"] = timeout
        return await client.request(
            method, path, params=params, content=body_bytes, headers=headers, **request_kwargs
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
        # Idempotent methods are retried on transport/5xx failures because a
        # request that never reached MAAS, or reached it but failed atomically,
        # is safe to replay. Writes are only retried for transient auth/session
        # failures (401 / session-flavored 403) where MAAS rejected the request
        # before any state change could occur.
        idempotent = method in {"GET", "HEAD", "DELETE"}

        last_exc: Exception | None = None
        attempt = 0
        while True:
            will_retry = attempt < _MAX_ATTEMPTS - 1
            try:
                response = await self._send(
                    method, path, params=params, json_body=json_body, timeout=timeout
                )
            except httpx.TransportError as exc:
                # Transport-level failure: timeout, connect, or read errors.
                # Log the real class so connect/DNS/TLS failures are not
                # misreported as timeouts.
                last_exc = exc
                retrying = idempotent and will_retry
                self._log_upstream(
                    method, path, f"<{type(exc).__name__}>", attempt, retrying=retrying
                )
                if not retrying:
                    break
                await self._sleep_backoff(attempt)
                attempt += 1
                continue

            if response.status_code >= 500:
                detail = _parse_upstream_error_message(response)
                last_exc = MCPUpstreamError(
                    f"upstream {response.status_code}",
                    status_code=response.status_code,
                    url=_url_without_query(response),
                    detail=detail,
                )
                # Deterministic failures (e.g. MAAS's bare 500 for a Django
                # DoesNotExist) can't heal under retry — fail fast so
                # downstream fallbacks run immediately.
                retrying = (
                    idempotent and will_retry and not _is_deterministic_500(detail)
                )
                self._log_upstream(
                    method, path, response.status_code, attempt, retrying=retrying
                )
                if not retrying:
                    break
                await self._sleep_backoff(attempt)
                attempt += 1
                continue

            if response.status_code >= 300:
                detail = _parse_upstream_error_message(response)
                upstream_exc = MCPUpstreamError(
                    f"upstream {response.status_code}",
                    status_code=response.status_code,
                    url=_url_without_query(response),
                    detail=detail,
                )
                # 401 and session-flavored 403 are safe to retry even for
                # writes: MAAS rejected the request before any mutation.
                retrying = will_retry and _is_retryable_auth_error(
                    response.status_code, detail
                )
                self._log_upstream(
                    method, path, response.status_code, attempt, retrying=retrying
                )
                if retrying:
                    last_exc = upstream_exc
                    await self._sleep_backoff(attempt)
                    attempt += 1
                    continue
                raise upstream_exc

            self._log_upstream(method, path, response.status_code, attempt, retrying=False)
            return self._parse_response(response)

        # Exhausted retries. The last upstream error surfaces verbatim; the
        # URL is reported without its query string — parameters may carry
        # user input. Distinguish true timeouts from other transport
        # failures so operators are not sent chasing the wrong cause.
        if isinstance(last_exc, MCPUpstreamError):
            raise last_exc
        if isinstance(last_exc, httpx.TimeoutException):
            raise MCPUpstreamTimeout(
                "upstream timed out after retries", url=path.split("?", 1)[0]
            ) from last_exc
        raise MCPUpstreamError(
            f"upstream unreachable: {type(last_exc).__name__}",
            status_code=0,
            url=path.split("?", 1)[0],
        ) from last_exc

    @staticmethod
    async def _sleep_backoff(attempt: int) -> None:
        """attempt is 0-indexed; we sleep before the NEXT attempt."""
        if attempt >= len(_RETRY_DELAYS_S):
            return
        await asyncio.sleep(_RETRY_DELAYS_S[attempt])

    def _auth_headers(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None,
        body: dict[str, Any] | None,
    ) -> dict[str, str]:
        if self._auth_mode == "api_key":
            if not self._cfg.api_key:
                raise RuntimeError("api_key auth mode selected but api_key is empty")
            return {"Authorization": f"Bearer {self._cfg.api_key}"}
        return self._oauth_header(method, path, params=params, body=body)

    def _oauth_header(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None,
        body: dict[str, Any] | None,
    ) -> dict[str, str]:
        # consumer_secret may be empty for the three-part triple API key
        # (PLAINTEXT with an empty consumer secret); token fields must be set.
        if not all([self._cfg.consumer_key, self._cfg.token_key, self._cfg.token_secret]):
            raise RuntimeError("oauth auth mode selected but token fields are incomplete")
        oauth_params = {
            "oauth_consumer_key": self._cfg.consumer_key or "",
            "oauth_token": self._cfg.token_key or "",
            "oauth_nonce": secrets.token_hex(16),
            "oauth_timestamp": str(int(time.time())),
            "oauth_signature_method": "PLAINTEXT",
            "oauth_version": "1.0",
        }
        # Per MAAS docs, the signature is PLAINTEXT: consumer_secret&token_secret.
        # An empty consumer_secret yields "&<token_secret>".
        oauth_params["oauth_signature"] = (
            f"{self._cfg.consumer_secret or ''}&{self._cfg.token_secret or ''}"
        )
        parts = ", ".join(
            f'{urllib.parse.quote(k, safe="")}="{urllib.parse.quote(v, safe="")}"'
            for k, v in sorted(oauth_params.items())
        )
        return {"Authorization": "OAuth " + parts}

    def _parse_response(self, response: httpx.Response) -> Any:
        if not response.content:
            return None
        # Some MAAS op-style endpoints (set_boot_disk, possibly others) return
        # literal "OK" text on success, not JSON. Detect JSON content by the
        # response's Content-Type; fall back to raw text otherwise.
        ctype = response.headers.get("content-type", "")
        if "json" in ctype.lower():
            try:
                return response.json()
            except json.JSONDecodeError as exc:
                raise MCPUpstreamError(
                    "upstream returned malformed JSON",
                    status_code=response.status_code,
                    url=_url_without_query(response),
                ) from exc
        return response.text

    def _log_upstream(
        self, method: str, path: str, status: Any, attempt: int, *, retrying: bool
    ) -> None:
        log.info(
            "maas_upstream_call",
            method=method,
            path=path,
            status=str(status),
            attempt=attempt,
            retrying=retrying,
        )


def _url_without_query(response: httpx.Response) -> str:
    """Request URL with the query string stripped.

    Query params may carry user input (hostnames, filters); credentials
    never travel in the URL, but dropping the query keeps error surfaces
    consistent with the timeout path, which only ever logs the path.
    """
    return str(response.request.url.copy_with(query=None))
