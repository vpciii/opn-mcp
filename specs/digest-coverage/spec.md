# Spec: Security-digest test coverage

- **Status:** Draft
- **Date:** 2026-07-12
- **Author:** vpc
- **Note:** Deliberately small — the first task in this repo dispatched to
  an agent-framework worker session (that framework's portability pilot).
  Additive only: characterization tests for the one tool both scheduled
  monitors depend on, which currently has none.

> This spec is editable while `Draft` / `Under review` / `Approved`.
> When it reaches `Implemented` it **freezes** into a historical record.

## Problem

`get_security_digest` is "the primary is-anything-wrong call" — both
scheduled monitors (docs/MONITORING.md) fast-path on its `warnings` list —
and it has zero test coverage. Its warning-emission behavior (which
scenarios produce warnings, which are deliberately suppressed as noise) is
enforced only by production use.

## Requirements

- **R-1 (MUST)** Characterization tests exercise `get_security_digest`
  against the mock transport (the `mock_opnsense` fixture pattern of
  `tests/test_harness.py`) — no live firewall, no changes to `server.py`.
- **R-2 (MUST)** The scenarios covered include at least: a clean system
  (no warnings); failed UI logins; denied admin actions; a stopped
  service; an expiring certificate; pending updates; and the WAN-block
  regimes — including that fewer than 200 WAN blocks emits **no** warning
  (deliberate noise suppression, per docs/MONITORING.md) while the
  higher regimes do.

## Success criteria

- **SC-1** — Tests in `tests/test_security_digest.py`, citing SC-1, cover
  every scenario in R-2 and pass against the mocked transport; the clean
  and suppressed-noise cases assert the *absence* of warnings, not just
  presence elsewhere. (R-1, R-2)

## Out of scope

- Any change to `server.py` or the digest's behavior — these tests
  characterize what exists; a behavior gap they reveal goes to a new
  spec/fix per the methodology, not into this slice.
- Severity tiering in code (the string-shaped warnings make that a
  structural design question — ADR territory, later).

## Traceability

| Criterion | Requirement(s) | Verified by (test) |
|---|---|---|
| SC-1 | R-1, R-2 | *(pending)* |
