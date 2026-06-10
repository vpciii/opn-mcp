FROM python:3.13-slim

# uv installs the exact dependency tree from uv.lock; --locked fails
# the build if the lockfile is stale vs pyproject.toml (spec SC-8,
# ADR 0004's pinned-tree claim made true). Note: --frozen would NOT
# catch staleness — it uses the lockfile without checking it.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project --compile-bytecode

COPY server.py .

CMD ["/app/.venv/bin/python", "server.py"]
