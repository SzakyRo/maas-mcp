FROM python:3.11-slim@sha256:9534e5a8e315485d4061ed659af0fd78a284c015f9b73661b41d6bab25604534

# Install pinned deps from uv.lock instead of re-resolving pyproject.toml at
# build time — an unpinned `pip install -e .` once pulled pydantic 2.13.x
# micro bumps that broke startup on this image's Python 3.11 while the dev
# environment (3.13) stayed green.
COPY --from=ghcr.io/astral-sh/uv:0.8@sha256:1d31be550ff927957472b2a491dc3de1ea9b5c2d319a9cea5b6a48021e2990a6 /uv /uvx /usr/local/bin/

WORKDIR /app

# Copy the package first so the dependency list in pyproject.toml is the
# single source of truth (no hand-mirrored pip install line to drift).
COPY pyproject.toml README.md uv.lock ./
COPY src/ ./src/

# Build/resolve inside the image so the lockfile is the source, not the
# host's resolver state. --no-editable avoids the /app/src symlink layout.
ENV UV_PROJECT_ENVIRONMENT=/usr/local
RUN uv sync --locked --no-dev --no-editable

# Expose the MCP server port
EXPOSE 8765

# Run the MCP server
CMD ["python", "-m", "maasmcp", "serve"]
