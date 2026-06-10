# Spec: Security posture hardening

- **Status:** Approved
- **Date:** 2026-06-09
- **Author:** vpc (drafted with Claude)
- **Related ADRs:** ADR-0002, ADR-0003, ADR-0004 (recorded posture being
  re-decided); superseding ADRs land with the implementation

> This spec is editable while `Draft` / `Under review` / `Approved`.
> When it reaches `Implemented` it **freezes** into a historical record;
> a contradiction found later goes to a test, a new spec, or an ADR —
> not back into this file (methodology §2, §8).

## Problem

The decision-capture ADRs (0002, 0003) recorded the pre-existing
security posture honestly and named its weak points as candidates for
re-deciding. Investigation of the code and the upstream OPNsense / MCP
SDK sources confirmed all three, and found two of them worse than
recorded:

- **SSE transport.** Documented and wired in `docker-compose.yml`, but
  the live deployment is the stdio Docker server; the pinned SDK now
  binds SSE to `127.0.0.1` inside the container, so the compose port
  mapping is almost certainly dead. The transport carries no auth of
  its own; if it were ever exposed, the write tool would be reachable
  by anyone who could reach the port. We maintain a risky, broken,
  unused surface.
- **TLS verification defaults off** (`OPNSENSE_VERIFY_SSL=false`), so
  any new deployment sends API credentials over unverified TLS unless
  the operator opts in. The live deployment already runs `true`, so the
  unsafe default protects nobody and endangers the next setup.
- **The anti-lockout guard is dead code.** It reads
  `rule_data.get("description")` but the OPNsense d_nat API field is
  `descr` — the guard has never matched any rule. Separately, when
  OPNsense refuses a toggle server-side (`{"result": "failed"}`), the
  tool wraps the failure in a success-shaped response and proceeds to
  call apply.
- **The deployed image's dependencies float.** The Dockerfile installs
  from `pyproject.toml` without `uv.lock`, contradicting what ADR 0004
  records about the pinned tree.

None of this is regression-protected: the repository has no tests and
no CI.

## Goals

1. The server exposes **no network listener**: stdio is the only
   transport, and the smallest possible remote attack surface is the
   documented posture.
2. **TLS verification is the default.** Self-signed OPNsense setups are
   supported properly (CA pinning), not by turning verification off.
3. `toggle_dnat_rule` **cannot endanger management access**, and a
   failed toggle is **reported as a failure**.
4. The deployed image runs the **locked dependency tree**.
5. The repository gains a **test harness and CI**, so every behavior
   above is regression-protected (the first tests in this repo).

## Non-goals

- No new remote transport and no auth design. If remote access is ever
  needed again, that is its own ADR with auth designed in from the
  start; until then, remote use goes through the operator's own channel
  (SSH, Tailscale) to a stdio server.
- No broader rule-management features (no rule creation/deletion, no
  additional write tools).
- No changes to OPNsense-side configuration.
- No audit of the read-only tools' endpoint coverage.

## Requirements

Non-functional requirements are stated where load-bearing. Each
`MUST` / `MUST NOT` is reflected in at least one success criterion
below (methodology §5, ADR 0011).

- **R-1 (MUST)** The server MUST NOT open any network listener. The
  `--sse` flag, the SSE path, and the compose SSE service are removed;
  invoking the retired flag fails with a clear error naming the
  alternative (stdio via the operator's own channel).
- **R-2 (MUST)** TLS verification MUST default to on.
  `OPNSENSE_VERIFY_SSL=false` remains available as an explicit,
  documented opt-out.
- **R-3 (MUST)** A CA bundle option (`OPNSENSE_CA_BUNDLE`) MUST be
  supported for self-signed setups, applied via an `ssl` context
  (`cafile`) — not the deprecated `verify=<str>` form, and not
  `SSL_CERT_FILE`, which httpx ignores under `trust_env=False`.
- **R-4 (MUST)** A TLS verification failure MUST produce an actionable
  error that names both remedies (CA bundle, explicit opt-out).
- **R-5 (MUST NOT)** `toggle_dnat_rule` MUST NOT act on OPNsense's
  synthetic anti-lockout rows. They are identified **structurally**
  (`lockout_*` pseudo-uuid / `is_automatic` flag), never by description
  text.
- **R-6 (MUST NOT)** `toggle_dnat_rule` MUST NOT act on rules whose
  destination targets the firewall's own management path (the
  firewall's own IPv4 addresses combined with the API port this server
  itself connects to). This is defense-in-depth for `noantilockout`
  configurations and management access on non-primary interfaces,
  which OPNsense's server-side protection does not cover.
- **R-7 (MUST)** A server-side toggle failure (`{"result": "failed"}`)
  MUST be reported as an error and MUST NOT trigger the apply step.
- **R-8 (MUST)** The Docker image MUST install the dependency tree from
  `uv.lock` (frozen), failing the build if the lockfile is stale.
- **R-9 (MUST)** Every behavior change above ships with a test that
  fails before and passes after; bug-fix PRs cite the failing run
  (methodology §5; global ADR 0015).
- **R-10 (SHOULD)** CI runs the test suite on every PR.
- **R-11 (SHOULD)** The README's SSE section is replaced with a short
  note on remote access via the operator's own channel to stdio;
  `docs/architecture.md`, `docs/glossary.md` (the anti-lockout entry
  currently describes the string match), `.env.example`, and
  `docs/MONITORING.md` are updated in the same PRs as the behavior they
  describe.

## Success criteria

Ids are append-only — never reuse or renumber.

- **SC-1** — Invoking the server with `--sse` exits with an error
  naming the stdio alternative; no code path can open a listener.
- **SC-2** — With no TLS-related env set, the HTTP client verifies
  certificates (no `CERT_NONE` context is constructed); the explicit
  `false` opt-out still works.
- **SC-3** — With `OPNSENSE_CA_BUNDLE=<path>`, the client verifies
  against that bundle via an `ssl` context, and connections succeed
  against a cert signed by it.
- **SC-4** — On verification failure, the error message names
  `OPNSENSE_CA_BUNDLE` and the explicit opt-out.
- **SC-5** — Toggling a synthetic lockout row (`lockout_*` /
  `is_automatic`) is refused client-side with a structural-guard error.
- **SC-6** — Toggling a rule whose destination matches the firewall's
  own IPv4 + the server's own API port is refused with the same guard.
- **SC-7** — When `toggleRule` returns `{"result": "failed"}`, the tool
  returns an error and no apply call is made (the regression test for
  the success-masking bug; red→green cited).
- **SC-8** — The Docker build installs exactly the `uv.lock` tree
  (frozen install) and fails on a stale lockfile.
- **SC-9** — CI runs the suite on PRs and fails on test failure.

## Open questions

All resolved 2026-06-09:

- [x] Live OPNsense version ≥ 26.1 — **confirmed**: the box runs
  26.1.9, and `/firewall/d_nat/searchRule` returns synthetic
  `lockout_0/1/2` rows. Note for implementation: `is_automatic` was
  `null` (not `true`) on the live rows, so the structural guard keys
  primarily on the `lockout_*` uuid prefix (R-5 permits either marker).
- [x] `descr` vs `description` — **confirmed against the live API**:
  rule rows carry `descr`; no `description` key exists. The dead-guard
  regression test stands on solid ground. (Upstream also marks the
  `descr` text gettext-translatable, so it is locale-dependent — a
  further reason text matching was never viable.)
- [x] `docker-compose.yml` — **remove entirely** (owner's decision,
  2026-06-09); the live deployment runs `docker run` stdio via the MCP
  client config.

## Out of scope (for now)

- A future authenticated remote transport (its own ADR, designed with
  auth from the start).
- Auditing `ping_host` / `get_updates_available(refresh=True)` —
  the action-triggering diagnostic POSTs recorded in ADR 0003 — beyond
  what this spec already covers.

## Traceability

Built up as the feature is implemented; complete before the spec is
marked `Implemented`. CI's coverage check governs this table.

| Criterion | Requirement(s) | Verified by (test) |
|---|---|---|
| SC-1 | R-1 | _TBD_ |
| SC-2 | R-2 | _TBD_ |
| SC-3 | R-3 | _TBD_ |
| SC-4 | R-4 | _TBD_ |
| SC-5 | R-5 | _TBD_ |
| SC-6 | R-6 | _TBD_ |
| SC-7 | R-7 | _TBD_ |
| SC-8 | R-8 | _TBD_ |
| SC-9 | R-9, R-10 | `tests/test_harness.py::test_suite_runs_async_against_mock_transport` (enforced by `.github/workflows/ci.yml`) |
