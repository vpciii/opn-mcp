# ADR 0006: Structural anti-lockout guard and honest toggle failures

- **Status:** Accepted
- **Date:** 2026-06-10
- **Deciders:** Vince Ciganik

## Context

ADR 0003 recorded the write tool's anti-lockout refusal and flagged
its mechanism — a string match on the rule description — as a known
limitation. Implementation of the hardening spec found it was worse
than weak: the guard read `rule["description"]`, but the d_nat API
field is `descr`, so **the guard had never matched any rule**. The
README's claim that "anti-lockout rules are protected" was untrue.

Two more facts from the investigation (verified against the live
26.1.9 box): OPNsense's anti-lockout protections surface in the d_nat
API as *synthetic* rows (`lockout_<n>` pseudo-uuids, locale-dependent
`descr`) that `toggleRule` refuses server-side with
`{"result": "failed"}` — and `toggle_dnat_rule` wrapped that refusal
in a success-shaped response and proceeded to call apply. Description
text is gettext-translated upstream, so a text guard is unreliable in
principle, not just misspelled in practice.

## Decision

`toggle_dnat_rule` refuses **structurally**, in three layers, and
reports failures honestly (spec R-5–R-7):

1. **Synthetic system rows**: uuids with the `lockout_` prefix are
   refused before any API call; a rule carrying a truthy
   `is_automatic` is refused likewise. No description text is ever
   consulted.
2. **Management-path rules**: a rule whose destination covers the
   firewall's own management path — its own IPv4 addresses (from
   interface statistics), interface-address tokens (`wanip`,
   `lanip`, …), `(self)`, `any`, or a CIDR containing an own address,
   on the API port this server itself connects to — is refused in
   both directions. This is defense-in-depth for `noantilockout`
   configurations and management on non-primary interfaces, which
   OPNsense's server-side protection does not cover.
3. **Honest failures**: a toggle whose result is missing or `failed`
   is returned as an error and the apply step is never reached. An
   empty `getRule` response (nonexistent uuid) errors before any
   mutation.

## Alternatives considered

- **Fix the field name, keep the text guard** — rejected: `descr` is
  locale-dependent (gettext), and the synthetic rows provide an exact
  structural marker.
- **Rely solely on OPNsense's server-side refusal** — rejected: it
  covers only the primary interface's lockout rows; the residual
  risks (R-6) are real, and the masking bug showed why client-side
  honesty matters regardless.
- **Direction-aware refusal** (allow *disabling* a management-path
  rule as a recovery action, refuse only enabling) — attractive, but
  R-6's agreed wording refuses acting in both directions. A
  relaxation is a spec contract change — its own diff for sign-off,
  deliberately not folded into this implementation.

## Consequences

- The README's protection claim is finally true, and provably so:
  regression tests cover the dead-guard and success-masking bugs
  (red→green cited in the PR), the synthetic-row refusal, the
  management-path refusal, and the ordinary-rule pass-through.
- Rules forwarding the API port on the firewall's own addresses can
  no longer be toggled through this server at all — including
  disabling one. The OPNsense GUI is the path for those; revisiting
  direction-awareness is a future spec change (above).
- Known limitation: alias-named destination ports/networks are not
  resolved (that would cost another API round-trip per toggle), so an
  alias that happens to contain the management port is not caught by
  layer 2. Layers 1 and 3 — and OPNsense's own server-side refusal —
  still apply.

This supersedes the guard-mechanism portion of ADR 0003; the rest of
that ADR (single curated write tool, "primarily read-only" posture)
stands.

## Adoption impact

Rebuild the Docker image to pick up the change. No configuration
changes; the tool's response shape is unchanged for permitted
toggles.

## References

- `specs/security-posture-hardening/spec.md` (R-5–R-7, SC-5–SC-7)
- ADR 0003 (superseded in part); `tests/test_toggle_guard.py`
- opnsense/core: synthetic lockout rows in `d_nat/searchRule`
  (issue #9514); `Util::getAntiLockout()`
