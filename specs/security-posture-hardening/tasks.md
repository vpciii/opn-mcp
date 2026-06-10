# Tasks: Security posture hardening

- **Status:** In progress
- **Spec:** ./spec.md
- **Plan:** ./plan.md

Each task below is one pull request. Keep each PR under ~300 lines of
diff where reasonable. Mark tasks as you go: `[ ]` → `[~]` (in
progress) → `[x]` (done, PR merged). Link the PR number when merged.

---

## Task 1 `[x]` — Bootstrap the test harness and CI

- **Depends on:** —
- **PR:** #7 (merged)

**What:** First tests in the repo: pytest + async runner + an
`httpx.MockTransport` fixture; extract import-time config globals into
a startup function (behavior-preserving); GitHub Actions workflow
running pytest and the spec-coverage checker (adapted from the
methodology reference, global ADR 0017).

**Acceptance criteria:**
- [x] `tests/` runs green locally and in CI on this PR (SC-9) — 5
      passed; CI run 27246211591 green
- [x] Config function returns the same values for the same env as the
      old globals (pinning test: `tests/test_config.py`)
- [x] Dev dependencies added to `pyproject.toml` dev group; `uv.lock`
      updated and committed
- [x] Spec-coverage checker wired in CI (governs this spec's
      Traceability from `Implemented` onward)
- [x] Tests verifying a spec criterion cite its id; Traceability table
      updated (SC-9 row)

---

## Task 2 `[x]` — TLS verification on by default + CA bundle

- **Depends on:** Task 1
- **PR:** #8 (merged)

**What:** Flip `OPNSENSE_VERIFY_SSL` default to `true`; add
`OPNSENSE_CA_BUNDLE` via `ssl.create_default_context(cafile=...)`;
actionable error on verification failure naming both remedies.

**Acceptance criteria:**
- [x] SC-2, SC-3, SC-4 tests pass; Traceability updated — red run:
      4 failed pre-change; green: 9 passed; CI run 27246481056
- [x] `README.md` TLS notes and `.env.example` updated in this PR
- [x] ADR 0005 (TLS verification posture; supersedes that part of
      ADR 0002) included
- [x] Breaking-change callout in the PR description (self-signed
      setups without a bundle) — `feat!:` + BREAKING CHANGE footer

---

## Task 3 `[x]` — Structural anti-lockout guard + honest failure reporting

- **Depends on:** Task 1
- **PR:** #9 (merged)

**What:** Replace the dead text guard with the structural check
(`lockout_*` uuid prefix primary, `is_automatic` secondary; refuse
destinations matching the firewall's own IPv4s + the server's own API
port); report `{"result": "failed"}` as an error and skip apply.

**Acceptance criteria:**
- [x] SC-5, SC-6, SC-7 tests pass; red→green evidence cited in the PR
      for the dead-guard and success-masking fixes (global ADR 0015) —
      red: 6 failed; green: 16 passed; CI run 27246753876
- [x] Pass-through case tested: an ordinary rule still toggles
      (`test_ordinary_rule_still_toggles`)
- [x] `docs/glossary.md` anti-lockout entry updated in this PR
- [x] ADR 0006 (structural guard + honest failures; supersedes the
      guard mechanism of ADR 0003) included; ADR 0003 status noted
- [x] Traceability updated (SC-5/6/7 rows)

---

## Task 4 `[x]` — Retire the SSE transport

- **Depends on:** Task 1
- **PR:** #10 (merged)

**What:** Remove `--sse` handling (clear exit message naming the stdio
alternative), delete `docker-compose.yml`, replace the README SSE
section with a remote-access-via-own-channel note.

**Acceptance criteria:**
- [x] SC-1 test passes; Traceability updated — red: 2 failed; green:
      18 passed; CI run 27247000529
- [x] `docker-compose.yml` deleted; `README.md` and
      `docs/architecture.md` updated in this PR (MONITORING.md needed
      no changes — its only matches were unrelated; architecture.md
      also caught up TLS/guard drift from tasks 2–3, noted in the PR)
- [x] ADR 0007 (stdio-only transport; supersedes that part of
      ADR 0002) included; ADR 0002 status noted

---

## Task 5 `[~]` — Pin the Docker image to uv.lock

- **Depends on:** Task 1
- **PR:** #11

**What:** Dockerfile installs the frozen `uv.lock` tree (build fails on
a stale lockfile), closing the drift against ADR 0004's pinned-tree
claim.

**Acceptance criteria:**
- [x] SC-8 verified (frozen install; stale lockfile fails the build) —
      both halves demonstrated locally and cited in PR #11; CI gains a
      docker-build step (run 27247259130 green); Traceability updated.
      Note: `uv sync --locked` is the staleness gate — `--frozen` does
      not check, which the negative test caught.
- [x] No new ADR (reality now matches what ADR 0004 already records)

---

## Wrap-up (rode with task 5's PR #11)

- [x] Every criterion in the spec's Traceability table maps to a
      passing test; coverage check green in CI (the checker enforces
      now that the spec is `Implemented` — and proved it by catching a
      malformed cell pre-push)
- [x] Spec and plan statuses → `Implemented` (frozen)
- [ ] Rebuild the live `opn-mcp` image once (rollout step from
      plan.md); MCP client config unchanged — after PR #11 merges
