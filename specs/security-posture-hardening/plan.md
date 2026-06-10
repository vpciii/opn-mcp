# Plan: Security posture hardening

- **Status:** Approved
- **Date:** 2026-06-09
- **Author:** vpc (drafted with Claude)
- **Spec:** ./spec.md
- **Related ADRs:** ADR-0002, ADR-0003, ADR-0004 (posture being
  re-decided); ADR-0005..0007 land with their tasks

> This plan freezes with its spec: editable while `Draft` / `Under
> review` / `Approved`, and a historical record once `Implemented`.
> A contradiction found later goes to a test, a new spec, or an ADR —
> not back into this file.

## Approach

Five PR-sized tasks. The test harness lands first because every
subsequent change must ship red→green against it (the repo has no
tests today). The behavior changes then land smallest-blast-radius
first: TLS defaults (a no-op for the live deployment), then the
anti-lockout guard (fixes two real bugs), then SSE retirement (removes
code and docs). The Dockerfile lockfile fix is independent and goes
last. Each behavior PR carries its superseding ADR and its doc updates
in the same PR.

One implementation wrinkle: configuration is read into module globals
at import time (`server.py:17-22`), which fights test isolation. Task 1
extracts config reading into a small function called at startup
(behavior-preserving; the suite proves it), so tests can vary env per
case without `importlib.reload` gymnastics.

## Components touched

- `server.py` — `_client()` TLS context; `toggle_dnat_rule` guard and
  failure propagation; `--sse` removal; config-read extraction.
- `Dockerfile` — frozen `uv.lock` install. `docker-compose.yml` —
  deleted (spec open-question resolution).
- `tests/` (new), `.github/workflows/ci.yml` (new),
  `scripts/check_spec_coverage.py` (adapted from the methodology's
  reference checker, ADR 0017 global).
- Docs, same PR as the behavior: `README.md`, `.env.example`,
  `docs/architecture.md`, `docs/glossary.md` (anti-lockout entry
  currently describes the string match), `docs/MONITORING.md`,
  `docs/adr/0005..0007`.

## Data model changes

None — the server is stateless. No new personal or regulated data; API
credentials remain env-only, unchanged.

## API changes

The env interface is the API surface:

- `OPNSENSE_VERIFY_SSL` — default flips `false` → `true`. **Breaking**
  for unverified self-signed setups; remedies (CA bundle, explicit
  opt-out) are documented and named in the error message. The live
  deployment already sets `true` — no impact.
- `OPNSENSE_CA_BUNDLE` — new, optional: path to a PEM bundle, applied
  via `ssl.create_default_context(cafile=...)` (the deprecated httpx
  `verify=<str>` form and `SSL_CERT_FILE` — ignored under
  `trust_env=False` — are both avoided).
- `--sse` — removed; invoking it exits with an error naming the stdio
  alternative.
- `toggle_dnat_rule` — two new refusal cases (structural guard) and
  honest propagation of `{"result": "failed"}`; response shapes
  otherwise unchanged.

## Alternatives considered

- **respx vs `httpx.MockTransport`** — MockTransport: ships with
  httpx, zero new dependencies (§10); respx adds nothing we need.
- **Fix the text guard's field name instead of going structural** —
  rejected: `descr` is gettext-translated upstream (locale-dependent),
  and the synthetic rows give an exact structural marker. R-5 forbids
  text matching.
- **Convert compose to stdio instead of removing** — resolved by the
  owner: remove; the live deployment is `docker run` stdio via the MCP
  client config.
- **`importlib.reload` in tests instead of a config function** —
  rejected: reload-based tests are order-sensitive and brittle; the
  tiny extraction is behavior-preserving and the suite proves it.

## Risks

| Risk | Likelihood | Impact | Mitigation |
| ---- | ---------- | ------ | ---------- |
| Guard false-positive blocks a legitimate toggle | Low | Med | Refuse only `lockout_*` uuids or destinations matching own-IP + the server's own API port; tests assert both refusal and pass-through cases (SC-5, SC-6). |
| Config extraction changes startup behavior | Low | Med | Pure refactor, same env names/defaults; harness lands first and pins behavior. |
| CA bundle misconfiguration confuses operators | Low | Low | SC-4: the failure message names both remedies. |
| `is_automatic` unreliable as a marker | Confirmed `null` on live rows | — | Guard keys primarily on the `lockout_*` uuid prefix (spec open-question resolution). |

## Rollout

One PR per task, in order; each independently revertible by `git
revert`. The live deployment sees no change until the image is rebuilt;
after task 2 a rebuild behaves identically (host already verifies),
after task 4 the unused `--sse` path is gone. Final step after task 5
merges: rebuild the `opn-mcp` image once; the MCP client config needs
no changes.

## Observability

The server is a stdio tool; error messages are the operational
surface. Guard refusals and TLS failures must be self-explanatory
(SC-4 tests the TLS message text; SC-5/SC-6 the guard's).

## Test strategy

Unit tests with pytest + the project's async runner (matching the
server's async tools) and `httpx.MockTransport` fixtures — no live-box
calls in CI. Critical cases: TLS context construction for each env
combination (default / `false` / CA bundle); guard refusal and
pass-through; failure propagation with apply-not-called asserted;
`--sse` exit. The dead-guard and success-masking fixes are regression
tests written red-first, failing runs cited in their PRs (R-9, global
ADR 0015). CI runs pytest plus the spec-coverage checker, which
governs this spec's Traceability table from `Implemented` onward.
