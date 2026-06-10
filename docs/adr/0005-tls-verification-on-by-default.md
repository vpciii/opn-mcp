# ADR 0005: TLS verification on by default, with CA pinning

- **Status:** Accepted
- **Date:** 2026-06-10
- **Deciders:** Vince Ciganik

## Context

ADR 0002 recorded the pre-existing posture: `OPNSENSE_VERIFY_SSL`
defaulted to `false`, so a fresh deployment sent API credentials over
unverified TLS unless the operator opted in — and named that default a
candidate for re-deciding. The security-posture-hardening spec
(R-2–R-4) makes the call. Two facts shaped it: the live deployment
already runs `verify=true` against a hostname certificate (the flip is
a production no-op), and the previous "self-signed support" was simply
verification turned off, not actual support.

Two implementation constraints worth recording: httpx's
`verify=<path>` string form is deprecated, and under `trust_env=False`
(ADR 0002) httpx ignores `SSL_CERT_FILE`/`SSL_CERT_DIR` — so a CA
bundle option must be a project env var fed into an `ssl` context.

## Decision

- **Verification is the default.** `OPNSENSE_VERIFY_SSL` defaults to
  `true`. Parsing is fail-safe: only the literal `false`
  (case-insensitive) disables verification; any other value verifies,
  so a typo cannot silently turn it off.
- **Self-signed and private-CA setups are supported properly** via
  `OPNSENSE_CA_BUNDLE=<path to CA PEM>`, applied with
  `ssl.create_default_context(cafile=...)`.
- **Verification failures are actionable**: the error names both
  remedies (`OPNSENSE_CA_BUNDLE`, explicit `OPNSENSE_VERIFY_SSL=false`).

This supersedes the TLS-verification-default portion of ADR 0002; the
rest of that ADR (env-only credentials, `trust_env=False`) stands.

## Alternatives considered

- **Keep default `false`** — rejected: protects no existing
  deployment and endangers every future one; "secure by default" is
  the methodology's stated posture (§9).
- **`SSL_CERT_FILE` for the bundle** — rejected: ignored by httpx
  under `trust_env=False`; would silently not work.
- **httpx `verify=<path>`** — rejected: deprecated upstream; the ssl
  context form is the supported path.
- **Tolerant boolean parsing** (`"no"`, `"0"` disable) — rejected: an
  unrecognized value falling toward "verify" is the only safe failure
  mode for a security toggle.

## Consequences

- **Breaking** for self-signed setups that relied on the old default:
  after upgrading they must set `OPNSENSE_CA_BUNDLE` (preferred) or
  explicitly opt out. The error message walks them to both.
- The live deployment is unaffected (already `true`).
- Verified by `tests/test_tls.py` (SC-2, SC-3, SC-4), including a real
  handshake against a private-CA server; the regression suite pins the
  fail-safe parsing.

## Adoption impact

Rebuild the Docker image to pick up the change; the live MCP client
config needs no edits. Self-signed setups: set `OPNSENSE_CA_BUNDLE`
(the PEM must be readable inside the container — mount it) or set
`OPNSENSE_VERIFY_SSL=false` explicitly.

## References

- `specs/security-posture-hardening/spec.md` (R-2–R-4, SC-2–SC-4)
- ADR 0002 (superseded in part), methodology §9
- `tests/test_tls.py`
