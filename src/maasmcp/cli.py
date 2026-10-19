"""maasmcp command-line interface."""

from __future__ import annotations

from pathlib import Path

import typer
from pydantic import ValidationError

app = typer.Typer(
    name="maasmcp",
    help="MCP server exposing Canonical MAAS bare-metal provisioning.",
    no_args_is_help=True,
)


@app.callback()
def _root() -> None:
    # An explicit callback keeps the app a command *group*; without it typer
    # collapses a single-command app so `maasmcp serve` is rejected as an
    # unexpected extra argument.
    pass


def _scrub_validation_error(exc: ValidationError) -> str:
    """Render a Pydantic ValidationError without echoing input= values.

    By default ValidationError.__str__ includes ``input=value`` for each
    error, which can leak secrets (api_key, consumer_secret, etc.) into
    startup logs. Replace each error with its location + msg only.
    """
    parts: list[str] = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err.get("loc", ()))
        msg = err.get("msg", "")
        parts.append(f"{loc}: {msg}" if loc else msg)
    return "; ".join(parts) or "configuration validation failed"


@app.command()
def serve(
    config: Path = typer.Option(  # noqa: B008
        None,
        "--config",
        "-c",
        help="Path to YAML config file. Falls back to MAASMCP_* env vars.",
    ),
) -> None:
    """Run the MCP streamable-HTTP server."""
    from maasmcp.config import MaasmcpConfig
    from maasmcp.server import run

    try:
        cfg = MaasmcpConfig.load(config)
    except ValidationError as exc:
        # Fail fast but do not echo input values (api_key, bearer_token, etc.)
        typer.echo(f"Configuration error: {_scrub_validation_error(exc)}", err=True)
        raise typer.Exit(code=2) from exc
    except RuntimeError as exc:
        # e.g. a ${VAR} placeholder in the YAML references an unset variable —
        # same fail-fast treatment (no traceback noise at startup).
        typer.echo(f"Configuration error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    run(cfg)


def main() -> None:
    """Console-script entry point."""
    app()


if __name__ == "__main__":
    main()
