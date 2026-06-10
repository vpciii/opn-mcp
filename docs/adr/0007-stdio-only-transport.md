# ADR 0007: Stdio-only transport — the SSE transport is retired

- **Status:** Accepted
- **Date:** 2026-06-10
- **Deciders:** Vince Ciganik

## Context

ADR 0002 recorded the SSE transport's posture honestly: it carried no
authentication of its own, relying entirely on assumed network
placement — and flagged it for re-deciding. The hardening spec's
investigation then established three facts:

- **It is unused.** The live deployment is the stdio Docker server;
  nothing consumes SSE.
- **It was probably already broken.** The pinned MCP SDK changed its
  default bind to `127.0.0.1` *inside the container*, making the
  compose file's `8000:8000` mapping dead — the README's SSE
  instructions likely hadn't worked since an image rebuild.
- **Hardening it is real work.** The SDK's auth support is
  OAuth-resource-server-shaped; a simple shared token needs a custom
  `TokenVerifier` or wrapping the SSE app in custom middleware —
  security-sensitive code maintained for a transport nobody uses.

We maintained a risky, broken, unused surface whose only honest fix
was either real auth work or removal.

## Decision

**The server is stdio-only and opens no network listener** (spec R-1).

- The `--sse` flag is removed; invoking it exits with an error naming
  the alternative (run the stdio server over your own channel — SSH,
  Tailscale — to the host).
- `docker-compose.yml` — whose sole purpose was the SSE service — is
  deleted (owner decision in the spec's open-question resolution).
- If a remote transport is ever needed again, it is a new ADR with
  authentication designed in from the start, not a revival of this
  one.

This supersedes the SSE-transport portion of ADR 0002; the credential
posture there (env-only secrets, `trust_env=False`) stands.

## Alternatives considered

- **Keep SSE, localhost-only** — minimal code, but keeps a listener
  code path alive for nobody, and "localhost-only" invites the next
  `FASTMCP_HOST=0.0.0.0` to undo it silently.
- **Keep SSE + bearer token** — workable (custom `TokenVerifier`),
  but adds security-sensitive code, tests, and rotation questions for
  a transport with zero current consumers. Rejected as maintenance
  without benefit; recorded as the starting point if remote access
  ever becomes real.
- **Repair the compose path** — rejected: it would re-expose the
  unauthenticated listener the spec exists to remove.

## Consequences

- The remote attack surface is zero: the write tool is reachable only
  by the process that spawns the server.
- Anyone following the old README's SSE instructions gets a clear
  error instead of a silently dead or silently exposed service.
- Remote use requires an operator-owned channel (SSH/Tailscale to the
  stdio host) — documented in the README.
- Removing rather than fixing is reversible the methodology's way: a
  future superseding ADR with auth designed in (git history retains
  the old wiring for reference).

## Adoption impact

Rebuild the Docker image. The live MCP client config (stdio `docker
run`) is unaffected. Anyone using compose for SSE (no known users)
migrates to the README's remote-access pattern.

## References

- `specs/security-posture-hardening/spec.md` (R-1, SC-1)
- ADR 0002 (superseded in part); `tests/test_transport.py`
- MCP python-sdk PR #738 (default bind change to 127.0.0.1)
