# Tasks: Security-digest test coverage

- **Status:** Approved
- **Spec:** ./spec.md
- **Plan:** — (single-file test slice; the spec's Requirements are the plan)

One task, dispatched to an agent-framework worker session.

---

### [ ] T-1 — Characterize get_security_digest's warning emission
- **Satisfies:** SC-1
- **Depends on:** —
- **Touches:** `tests/test_security_digest.py` (new),
  `specs/digest-coverage/spec.md` (replace the SC-1 Traceability row's
  `*(pending)*` with your citing tests, full `path::test_name`)
- **Brief:** Add characterization tests for `server.get_security_digest`
  using the existing `mock_opnsense` fixture (see `tests/conftest.py` and
  the pattern in `tests/test_harness.py`): your handler routes by
  `request.url.path` and returns canned JSON per endpoint — read
  `get_security_digest` and its `_scan_*` helpers in `server.py` to see
  which endpoints it sweeps and what shapes it expects. Cover, at
  minimum: a clean system (assert `warnings == []`); failed UI logins;
  denied admin actions; a stopped service; a certificate near expiry;
  pending updates; WAN-origin blocks in the suppressed regime (< 200 —
  assert NO warning is emitted) and in a warning regime (≥ 200). Do NOT
  modify `server.py` or any other production file — if the digest's
  behavior surprises you, that is escalation material, not something to
  fix here. Tests are async (`asyncio_mode = "auto"`).
- **Done when:** tests citing SC-1 pass via `uv run pytest`; the spec's
  Traceability row cites them; nothing outside the two Touches files
  changed.

---

## Criterion → task map

| Criterion | Requirement(s) | Task | Status |
|---|---|---|---|
| SC-1 | R-1, R-2 | T-1 | pending |
