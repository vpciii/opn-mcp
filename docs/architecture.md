# Architecture — opn-mcp

- **Updated:** 2026-06-09 — changes in the **same PR** as the structure
  it describes (methodology §2).

A short, current-state overview of how the system is shaped **now**,
reverse-engineered from the code at adoption time (`adopting.md` seed
step 1). This is a *navigational* document, not a decision log: it says
*what* the system is and points at `docs/adr/` for *why*. Unknowns are
marked as unknown — partial-but-honest beats exhaustive-but-stale.

## What this is

An MCP server that exposes monitoring tools for a single OPNsense
firewall over its REST API — primarily read-only, with one narrow write
operation (`toggle_dnat_rule`). Consumed by MCP clients: Claude Desktop,
Claude Code, and scheduled Claude Code agents doing hands-off security
monitoring.

## System context

```
[ MCP client (Claude Desktop / Claude Code /        stdio  or  SSE :8000
  scheduled security-check & daily-summary agents) ] ──────► [ opn-mcp ]
                                                                  │
                                                                  │ HTTPS + API key/secret
                                                                  ▼
                                                        [ OPNsense REST API ]
```

The scheduled agents (see `docs/MONITORING.md`) additionally push
notifications via a separate Home Assistant MCP server (`ha-mcp`); that
hop is outside this repo.

## Major components

The runtime is a single Python module; the rest is packaging and
host-side operational tooling.

| Component | Responsibility | Lives in |
|---|---|---|
| Tool layer | ~24 `@mcp.tool()` functions (status/inventory, security monitoring incl. `get_security_digest`, firewall/NAT, VPN, logs); the sole write tool `toggle_dnat_rule` refuses anti-lockout rules | `server.py` |
| HTTP client layer | `_client()` / `_get()` / `_post()`: per-call `httpx.AsyncClient` with basic auth, configurable TLS verify, `trust_env=False` | `server.py` |
| Log parsing & aggregation | Audit-login / filterlog parsers, WAN- vs LAN-origin block splitting, cert-expiry and config-change checks feeding the security digest | `server.py` |
| Transport entrypoint | `FastMCP("opn-mcp")`; stdio by default, `--sse` serves SSE on port 8000 | `server.py`, `Dockerfile`, `docker-compose.yml` |
| Scheduled-task skills | Prompt/skill definitions for the hourly security-check and daily-summary agents that *consume* this server | `scheduled-tasks/`, `docs/scheduled-tasks/`, `docs/MONITORING.md` |
| Host cleanup script | launchd job reaping zombie scheduled-task `claude` processes and stale containers on the host | `scripts/` |

## Data stores

None. The server is stateless: no database, cache, queue, or file
persistence; every tool call opens a fresh HTTP client and proxies to
OPNsense. The firewall's own config and logs are the source of truth
for everything the tools report.

| Store | Holds | Source of truth for |
|---|---|---|
| — (none) | — | OPNsense itself holds all state |

## External dependencies

Recorded as a decision-capture ADR: `docs/adr/0004`.

- **OPNsense REST API** — the only external service; every tool is a
  view over it. Endpoint availability varies with OPNsense version and
  installed plugins (e.g. `os-tailscale`).
- **`mcp[cli]` (FastMCP)** — MCP protocol server and both transports.
- **`httpx`** — async HTTP client to OPNsense; `trust_env=False` to
  bypass proxy env vars (see README troubleshooting).
- **Docker / docker-compose** — packaging for the stdio (Claude
  Desktop) and SSE (persistent service) deployment modes.
- Lockfile: `uv.lock` (committed).

## Trust boundaries

Recorded as decision-capture ADRs: `docs/adr/0002` (credentials,
TLS verify, SSE) and `docs/adr/0003` (write surface).

- **MCP client → server.** Untrusted/LLM-driven input enters here (tool
  arguments, e.g. `ping_host(target)`, `get_log` filters,
  `toggle_dnat_rule(uuid)`). The server adds **no authentication of its
  own**: stdio trusts the spawning process; the SSE transport on port
  8000 is open to anyone who can reach it. The README assumes network
  placement (LAN/Tailscale) provides that boundary — the actual
  deployment is **not determined from the repo**.
- **Server → OPNsense.** Credentials are an OPNsense API key/secret
  from env vars only (`.env` is gitignored; never in the repo). TLS
  verification is **off by default** (`OPNSENSE_VERIFY_SSL=false`, for
  self-signed certs).
- **Authorization.** Effective privileges are whatever the OPNsense API
  user has — the README recommends a read-only group, but the actual
  privilege set is **unknown from the repo**. Server-side, the write
  surface is limited to `toggle_dnat_rule`, which fetches the rule
  first and refuses any whose description matches anti-lockout.
- **Key rotation practice** — not determined from the repo.

## Shape-defining decisions

Decision-capture ADRs (`adopting.md` seed step 3), each recording a
pre-existing decision:

- **ADR 0001** — stateless single-module MCP proxy over the OPNsense
  REST API (stdio default, SSE opt-in).
- **ADR 0002** — credential and transport security posture (env-var
  secrets, `trust_env=False`, TLS-verify-off default, unauthenticated
  SSE relying on network placement); the two defaults are flagged as
  candidates for superseding ADRs.
- **ADR 0003** — single curated write tool (`toggle_dnat_rule`) with
  anti-lockout refusal.
- **ADR 0004** — runtime dependencies and packaging (`mcp[cli]`,
  `httpx`, uv lockfile, Docker/compose).
