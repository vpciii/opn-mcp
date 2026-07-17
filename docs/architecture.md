# Architecture — opn-mcp

- **Updated:** 2026-07-17 — changes in the **same PR** as the structure
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
[ MCP client (Claude Desktop / Claude Code /              stdio only
  scheduled security-check & daily-summary agents) ] ──────► [ opn-mcp ]
                                                                  │
                                                                  │ HTTPS (verified) + API key/secret
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
| Tool layer | ~24 `@mcp.tool()` functions (status/inventory, security monitoring incl. `get_security_digest`, firewall/NAT, VPN, logs); the sole write tool `toggle_dnat_rule` refuses anti-lockout and management-path rules structurally (ADR 0006) | `server.py` |
| HTTP client layer | `_client()` / `_get()` / `_post()`: per-call `httpx.AsyncClient` with basic auth, TLS verified by default with optional CA pinning (ADR 0005), `trust_env=False`, HTTP/2 negotiated via ALPN (ADR 0010) | `server.py` |
| Log parsing & aggregation | Audit-login / filterlog parsers, WAN- vs LAN-origin block splitting, cert-expiry and config-change checks feeding the security digest | `server.py` |
| Transport entrypoint | `FastMCP("opn-mcp")`; stdio only — no network listener (ADR 0007) | `server.py`, `Dockerfile` |
| Tests & CI | pytest suite (`httpx.MockTransport`, no live box) + spec-criterion coverage check on every PR | `tests/`, `scripts/`, `.github/workflows/` |
| Scheduled-task skills | Prompt/skill definitions for the hourly security-check and daily-summary agents that *consume* this server; `scheduled-tasks/<id>/SKILL.md` is the single source (ADR 0008) | `scheduled-tasks/`, `docs/MONITORING.md` |
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
- **`mcp[cli]` (FastMCP)** — MCP protocol server, stdio transport.
- **`httpx[http2]`** — async HTTP client to OPNsense; `trust_env=False`
  to bypass proxy env vars (see README troubleshooting); the `http2`
  extra (`h2`/`hpack`/`hyperframe`) because OPNsense 26.7 mis-frames
  large HTTP/1.1 chunked responses (ADR 0010).
- **Docker** — packaging for the stdio (Claude Desktop / Claude Code)
  deployment mode.
- Lockfile: `uv.lock` (committed).

## Trust boundaries

Recorded in ADRs: `docs/adr/0002` (credentials; superseded in part by
0005 and 0007), `docs/adr/0005` (TLS), `docs/adr/0006` (write surface),
`docs/adr/0007` (transport).

- **MCP client → server.** Untrusted/LLM-driven input enters here (tool
  arguments, e.g. `ping_host(target)`, `get_log` filters,
  `toggle_dnat_rule(uuid)`). The transport is **stdio only** — the
  server opens no network listener, so the only client is the process
  that spawned it (ADR 0007).
- **Server → OPNsense.** Credentials are an OPNsense API key/secret
  from env vars only (`.env` is gitignored; never in the repo). TLS is
  **verified by default**; self-signed setups pin a CA via
  `OPNSENSE_CA_BUNDLE`, and `OPNSENSE_VERIFY_SSL=false` is the explicit
  opt-out (ADR 0005).
- **Authorization.** Effective privileges are whatever the OPNsense API
  user has — the README recommends a read-only group, but the actual
  privilege set is **unknown from the repo**. Server-side, the write
  surface is limited to `toggle_dnat_rule`, which refuses synthetic
  anti-lockout rows and rules covering the firewall's own management
  path structurally, and treats server-side toggle failures as errors
  (ADR 0006).
- **Key rotation practice** — not determined from the repo.

## Shape-defining decisions

- **ADR 0001** — stateless single-module MCP proxy over the OPNsense
  REST API (decision capture).
- **ADR 0002** — credential posture: env-var secrets, `trust_env=False`
  (decision capture; TLS default superseded by 0005, SSE by 0007).
- **ADR 0003** — single curated write tool (`toggle_dnat_rule`)
  (decision capture; guard mechanism superseded by 0006).
- **ADR 0004** — runtime dependencies and packaging (`mcp[cli]`,
  `httpx`, uv lockfile, Docker).
- **ADR 0005** — TLS verification on by default, CA pinning via
  `OPNSENSE_CA_BUNDLE`.
- **ADR 0006** — structural anti-lockout / management-path guard and
  honest toggle failures.
- **ADR 0007** — stdio-only transport; the SSE transport retired.
- **ADR 0010** — HTTP/2 to the OPNsense API (works around 26.7's
  malformed HTTP/1.1 chunked framing on large responses).
