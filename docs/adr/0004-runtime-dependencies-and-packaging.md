# ADR 0004: Runtime dependencies and packaging

- **Status:** Accepted
- **Date:** 2026-06-09
- **Deciders:** Vince Ciganik

> This ADR **records a pre-existing decision** rather than making a new
> one (brownfield decision capture, methodology §10 / `adopting.md`
> seed step 3). One combined record for the small, stable dependency
> set.

## Context

The runtime needs an MCP protocol implementation with stdio and SSE
transports, and an async HTTP client for the OPNsense API. Methodology
§10 treats dependencies as decisions worth recording.

## Decision

We depend on exactly two runtime packages — **`mcp[cli]>=1.0.0`**
(FastMCP server + both transports) and **`httpx>=0.27.0`** (async
HTTP) — managed with **uv** and a committed `uv.lock`. Packaging is a
slim **Docker** image (python:3.12-slim, pip-installed) run either
per-session by Claude Desktop (stdio) or as a persistent
`docker-compose` service (SSE).

## Alternatives considered

- **Hand-rolled MCP over JSON-RPC** — no dependency, but reimplements
  a moving protocol; the official SDK tracks spec changes for us.
- **`requests`/`aiohttp` instead of `httpx`** — `requests` is sync
  (blocks the async server); `httpx` gives async, timeouts, and
  per-client `trust_env` control in one package.
- **No container (bare `pip install .`)** — still supported for local
  runs, but Docker gives Claude Desktop a reproducible spawn target
  and compose gives the SSE service restart-on-failure.

## Consequences

- Easier: tiny supply-chain surface (two direct deps, both
  permissively licensed and actively maintained); `uv.lock` pins the
  full tree; image rebuilds are fast.
- Harder: tied to the `mcp` SDK's release cadence and any FastMCP API
  churn; Docker image must be rebuilt for code changes to reach
  Claude Desktop (a recurring troubleshooting item in the README).

## Adoption impact

None — records the dependency set already in `pyproject.toml` /
`uv.lock`. Future non-trivial dependency additions get their own ADRs
(methodology §10).

## References

- `pyproject.toml`, `uv.lock`, `Dockerfile`, `docker-compose.yml`
- ADR 0001 (FastMCP as the server framework)
