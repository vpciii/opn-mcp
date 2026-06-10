# ADR 0002: Credential and transport security posture

- **Status:** Accepted
- **Date:** 2026-06-09
- **Deciders:** Vince Ciganik

> This ADR **records a pre-existing decision** rather than making a new
> one (brownfield decision capture, `adopting.md` seed step 3). It
> changes no code or defaults.

## Context

The server authenticates to a home-lab OPNsense box that typically
runs a self-signed certificate, from clients on a LAN or Tailscale
network. Secrets must stay out of the repo; the deployment context is
a trusted private network, not the public internet.

## Decision

We read the OPNsense API key/secret from environment variables only
(`OPNSENSE_API_KEY` / `OPNSENSE_API_SECRET`; `.env` is gitignored).
The httpx client sets `trust_env=False` (proxy env vars ignored).
`OPNSENSE_VERIFY_SSL` defaults to **`false`** — TLS certificate
verification is off unless explicitly enabled. The SSE transport
carries **no authentication of its own**; anyone who can reach port
8000 can use every tool. Network placement (LAN/Tailscale) is assumed
to provide that boundary.

## Alternatives considered

- **Verify TLS by default** — safer, but fails out of the box against
  the self-signed certs typical of home OPNsense installs; convenience
  won.
- **Authenticated SSE (token/mTLS/reverse proxy)** — rejected at the
  time as ceremony for a single-user Tailscale deployment.
- **Secrets file / secret manager** — env vars were the simplest thing
  compatible with Docker and `docker-compose` `env_file`.

## Consequences

- Easier: zero-friction setup against self-signed certs; secrets never
  touch the repo; proxy env weirdness (OrbStack `NO_PROXY`) can't break
  the client.
- Risks, stated plainly:
  - With `OPNSENSE_VERIFY_SSL=false`, the API key/secret travel over
    **unverified TLS** — an on-path attacker (MITM) on the network
    could impersonate the firewall and capture them.
  - If the SSE port is ever reachable beyond the trusted network, the
    full tool surface — including the write tool (ADR 0003) — is
    **unauthenticated**.
- **Both defaults are candidates for re-deciding via a superseding
  ADR**: verify-TLS-on-by-default (with a documented opt-out), and
  some form of auth on SSE. Neither is changed here.

## Adoption impact

None — records the existing posture; any change to it is a future
superseding ADR plus code change.

## References

- `server.py` (`_client()`, configuration block)
- `docs/architecture.md` — "Trust boundaries"
- `README.md` — setup and OrbStack troubleshooting
