"""Pydantic Settings configuration with ${VAR} expansion."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, ClassVar

import yaml
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

logger = logging.getLogger(__name__)

_PLACEHOLDER_RE = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")


def _expand_env(text: str) -> str:
    """Expand ${VAR} placeholders, raising RuntimeError on missing vars."""

    def repl(match: re.Match[str]) -> str:
        var = match.group(1)
        try:
            return os.environ[var]
        except KeyError as exc:
            raise RuntimeError(
                f"Environment variable {var} is referenced in config but not set"
            ) from exc

    return _PLACEHOLDER_RE.sub(repl, text)


def _expand_recursive(node: Any) -> Any:
    """Recursively expand ${VAR} placeholders in all string leaves."""
    if isinstance(node, str):
        return _expand_env(node)
    if isinstance(node, dict):
        return {k: _expand_recursive(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_expand_recursive(v) for v in node]
    return node


def _yaml_load_with_expansion(path: Path) -> dict[str, Any]:
    """Load YAML with ${VAR} expansion on every string leaf."""
    text = path.read_text()
    data = yaml.safe_load(text)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise RuntimeError(f"Top-level YAML in {path} must be a mapping, got {type(data).__name__}")
    return _expand_recursive(data)  # type: ignore[no-any-return]


class MaasConfig(BaseSettings):
    """MAAS upstream connection settings.

    Authentication modes (validated by :meth:`_split_api_key_triple`):

    - ``api_key``: a single Bearer-style API key (used by newer MAAS).
    - ``oauth``: full four-field OAuth1 credentials (consumer_key,
      consumer_secret, token_key, token_secret).
    - ``api_key_triple``: MAAS's compact ``consumer_key:token_key:token_secret``
      string where the consumer_secret is empty — equivalent to OAuth1
      PLAINTEXT with an empty consumer secret. Auto-split into the four
      OAuth fields at validation time.
    """

    base_url: str = Field(..., description="MAAS root URL, e.g. https://maas.example.com/MAAS")
    api_key: str | None = Field(default=None, description="MAAS API key (api_key mode)")
    consumer_key: str | None = Field(default=None, description="OAuth consumer key (oauth mode)")
    consumer_secret: str | None = Field(default=None, description="OAuth consumer secret")
    token_key: str | None = Field(default=None, description="OAuth token key")
    token_secret: str | None = Field(default=None, description="OAuth token secret")
    api_version: str = Field(default="2.0")
    verify_tls: bool = Field(default=True)
    # Set true to allow credentials to travel over plain http://. Default false:
    # OAuth PLAINTEXT and Bearer tokens are sent in the Authorization header,
    # which any on-path party can read over http://. Explicitly opt-in only —
    # e.g. for a MAAS-on-local-network dev box behind a private tunnel.
    allow_insecure: bool = Field(default=False)

    @field_validator("base_url")
    @classmethod
    def _strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")

    @model_validator(mode="before")
    @classmethod
    def _split_api_key_triple(cls, data: Any) -> Any:
        """Split a three-part ``consumer:token:token_secret`` api_key into OAuth fields.

        MAAS issues API keys in the compact form
        ``"<consumer_key>:<token_key>:<token_secret>"`` with an empty
        consumer_secret. Newer MAAS deployments sometimes issue a raw
        opaque Bearer key. We detect the three-part shape by counting
        colons: a string with exactly two colons and no consumer_*/token_*
        fields populated is treated as the triple and split into the four
        OAuth credential fields. PLAINTEXT signatures use ``"&<token_secret>"``
        which yields the same wire format as the four-field config with
        consumer_secret="".

        Runs in ``before`` mode and returns a NEW dict (never mutates an
        existing model): a dumped/logged MaasConfig always reflects the
        derived OAuth fields, not a half-rewritten hybrid.
        """
        if not isinstance(data, dict):
            return data
        api_key = data.get("api_key")
        if not isinstance(api_key, str) or not api_key:
            return data
        parts = api_key.split(":")
        if len(parts) != 3:
            # Either a plain opaque Bearer key (1 part) or something
            # unexpected. Leave it for MaasClient to handle as Bearer.
            return data
        # If the user already supplied explicit OAuth fields, the api_key
        # is just a leftover bearer value — keep it as Bearer.
        if any(
            data.get(f) for f in ("consumer_key", "consumer_secret", "token_key", "token_secret")
        ):
            return data
        # MAAS triple parts are alphanumeric (hex-ish). A colon-bearing key
        # with any other character is an opaque Bearer key — treat it as
        # such rather than silently splitting it into wrong OAuth fields.
        if not all(re.fullmatch(r"[A-Za-z0-9]+", part) for part in parts):
            return data
        logger.info("api_key interpreted as MAAS OAuth triple (consumer:token:secret)")
        consumer_key, token_key, token_secret = parts
        # PLAINTEXT signature is "&<consumer_secret>&<token_secret>"; with
        # an empty consumer_secret that becomes "&<token_secret>". Clear
        # api_key so MaasClient._resolve_auth_mode doesn't see both auth
        # modes populated.
        return {
            **data,
            "consumer_key": consumer_key,
            "consumer_secret": "",
            "token_key": token_key,
            "token_secret": token_secret,
            "api_key": None,
        }


class ServerConfig(BaseSettings):
    """HTTP server settings."""

    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8765, ge=1, le=65535)
    # min_length=1 is the only hard gate: an empty expected token would
    # authenticate headerless requests because both sides compare with
    # hmac.compare_digest. Short tokens are permitted (user's network, user's
    # call) — for anything beyond a trusted LAN, generate one with
    # `openssl rand -hex 16` or longer.
    bearer_token: str = Field(..., min_length=1)
    log_level: str = Field(default="info")
    # Default raised 60→300s: lets individual MAAS API calls take up to 5
    # minutes (covers slow BMC probes under load). The MCP transport session
    # timeout is a separate, larger ceiling on the *tool* call itself.
    request_timeout_seconds: int = Field(default=300, ge=1)
    max_paginated_items: int = Field(default=1000, ge=1)


class MaasmcpSettingsSource(PydanticBaseSettingsSource):
    """Custom settings source registered alongside the built-in env source.

    The simpler loader design expands YAML placeholders inside
    :meth:`MaasmcpConfig.load` and validates the result via ``model_validate``,
    so this source intentionally contributes nothing in ``__call__``. It
    exists primarily to satisfy the contract that ``MaasmcpConfig`` registers
    a custom source distinct from the built-in env source.
    """

    def __init__(self, settings_cls: type[BaseSettings]) -> None:
        super().__init__(settings_cls)

    def get_field_value(self, field: Any, field_name: str) -> Any:
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        return {}


class MaasmcpConfig(BaseSettings):
    """Top-level maasmcp configuration."""

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix="MAASMCP_",
        env_nested_delimiter="__",
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    maas: MaasConfig
    server: ServerConfig

    @classmethod
    def load(cls, config_path: Path | None) -> MaasmcpConfig:
        """Load configuration from a YAML file (or env if path is None).

        YAML values containing ``${VAR}`` are expanded from the process
        environment before nested model validation. When ``config_path`` is
        ``None``, only environment variables (with the ``MAASMCP_`` prefix
        and ``__`` nested delimiter) are consulted.
        """
        if config_path is None:
            return cls()  # type: ignore[call-arg]
        data = _yaml_load_with_expansion(config_path)
        return cls.model_validate(data)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource | None = None,
        env_settings: PydanticBaseSettingsSource | None = None,
        dotenv_settings: PydanticBaseSettingsSource | None = None,
        file_secret_settings: PydanticBaseSettingsSource | None = None,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Register :class:`MaasmcpSettingsSource` alongside env settings.

        The built-in dotenv and file-secret sources are kept (dropping them
        would silently disable ``.env`` support for the env-only load mode).
        """
        yaml_source = MaasmcpSettingsSource(settings_cls)
        sources = [
            s
            for s in (
                init_settings,
                env_settings,
                dotenv_settings,
                file_secret_settings,
                yaml_source,
            )
            if s is not None
        ]
        return tuple(sources)
