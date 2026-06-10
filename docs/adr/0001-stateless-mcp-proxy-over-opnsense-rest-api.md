# ADR 0001: Stateless MCP proxy over the OPNsense REST API

- **Status:** Accepted
- **Date:** 2026-06-09
- **Deciders:** Vince Ciganik

> This ADR **records a pre-existing decision** rather than making a new
> one (brownfield decision capture, `adopting.md` seed step 3).

## Context

The project needs to expose OPNsense firewall monitoring to MCP
clients (Claude Desktop, Claude Code, scheduled agents). The firewall
already holds all state — config, logs, counters — behind its REST
API, and the consumers are LLM agents that work best with curated,
purpose-shaped responses rather than raw API payloads.

## Decision

We built a single Python module (`server.py`) on FastMCP: ~25 curated
`@mcp.tool()` functions, each opening a fresh `httpx.AsyncClient` per
call and proxying to the OPNsense REST API. The server keeps **no
local state** — no database, cache, queue, or files; OPNsense is the
source of truth for everything reported. Transport is stdio by
default, with SSE (port 8000) opt-in via `--sse`.

## Alternatives considered

- **Stateful / caching design** — caching firmware status, logs, or
  parsed digests would cut API round-trips and latency. Rejected:
  monitoring data goes stale fast, cache invalidation adds complexity,
  and a stateless server restarts/redeploys with zero migration cost.
- **Generic REST passthrough tool** — one `call_opnsense(path, body)`
  tool would cover every endpoint with no per-tool code. Rejected: it
  hands an LLM the firewall's full (write-capable) API surface, loses
  the curated aggregation that makes responses useful (digest,
  block-splitting, cert classification), and makes the safety posture
  (ADR 0003) unenforceable.

## Consequences

- Easier: deploys and restarts are trivial; no state to corrupt or
  migrate; every tool is independently understandable; behavior is
  fully determined by OPNsense plus the code.
- Harder: every call pays full HTTP round-trips (the digest makes
  several); a new endpoint means writing a new tool; a single module
  will get unwieldy if the tool count keeps growing.
- Constraint: anything needing history (trends, baselines) must live
  outside this server — e.g. in the scheduled agents that consume it.

## Adoption impact

None — records the shape the code already has.

## References

- `server.py` (tool layer, `_client()`/`_get()`/`_post()`)
- `docs/architecture.md` — "Major components", "Data stores"
