# Tasks: Security posture hardening

- **Status:** Under review
- **Spec:** ./spec.md
- **Plan:** ./plan.md

Each task below is one pull request. Keep each PR under ~300 lines of
diff where reasonable. Mark tasks as you go: `[ ]` → `[~]` (in
progress) → `[x]` (done, PR merged). Link the PR number when merged.

---

## Task 1 — Bootstrap the test harness and CI

- **Depends on:** —
- **PR:** —

**What:** First tests in the repo: pytest + async runner + an
`httpx.MockTransport` fixture; extract import-time config globals into
a startup function (behavior-preserving); GitHub Actions workflow
running pytest and the spec-coverage checker (adapted from the
methodology reference, global ADR 0017).

**Acceptance criteria:**
- [ ] `tests/` runs green locally and in CI on this PR (SC-9)
- [ ] Config function returns the same values for the same env as the
      old globals (pinning test)
- [ ] Dev dependencies added to `pyproject.toml` dev group; `uv.lock`
      updated and committed
- [ ] Spec-coverage checker wired in CI (governs this spec's
      Traceability from `Implemented` onward)
- [ ] Tests verifying a spec criterion cite its id; Traceability table
      updated (SC-9 row)

---

## Task 2 — TLS verification on by default + CA bundle

- **Depends on:** Task 1
- **PR:** —

**What:** Flip `OPNSENSE_VERIFY_SSL` default to `true`; add
`OPNSENSE_CA_BUNDLE` via `ssl.create_default_context(cafile=...)`;
actionable error on verification failure naming both remedies.

**Acceptance criteria:**
- [ ] SC-2, SC-3, SC-4 tests pass; Traceability updated
- [ ] `README.md` TLS notes and `.env.example` updated in this PR
- [ ] ADR 0005 (TLS verification posture; supersedes that part of
      ADR 0002) included
- [ ] Breaking-change callout in the PR description (self-signed
      setups without a bundle)

---

## Task 3 — Structural anti-lockout guard + honest failure reporting

- **Depends on:** Task 1
- **PR:** —

**What:** Replace the dead text guard with the structural check
(`lockout_*` uuid prefix primary, `is_automatic` secondary; refuse
destinations matching the firewall's own IPv4s + the server's own API
port); report `{"result": "failed"}` as an error and skip apply.

**Acceptance criteria:**
- [ ] SC-5, SC-6, SC-7 tests pass; red→green evidence cited in the PR
      for the dead-guard and success-masking fixes (global ADR 0015)
- [ ] Pass-through case tested: an ordinary rule still toggles
- [ ] `docs/glossary.md` anti-lockout entry updated in this PR (it
      currently describes the string match)
- [ ] ADR 0006 (structural guard + honest failures; supersedes the
      guard mechanism of ADR 0003) included
- [ ] Traceability updated

---

## Task 4 — Retire the SSE transport

- **Depends on:** Task 1
- **PR:** —

**What:** Remove `--sse` handling (clear exit message naming the stdio
alternative), delete `docker-compose.yml`, replace the README SSE
section with a remote-access-via-own-channel note.

**Acceptance criteria:**
- [ ] SC-1 test passes; Traceability updated
- [ ] `docker-compose.yml` deleted; `README.md`, `docs/MONITORING.md`,
      `docs/architecture.md` updated in this PR
- [ ] ADR 0007 (stdio-only transport; supersedes that part of
      ADR 0002) included

---

## Task 5 — Pin the Docker image to uv.lock

- **Depends on:** Task 1
- **PR:** —

**What:** Dockerfile installs the frozen `uv.lock` tree (build fails on
a stale lockfile), closing the drift against ADR 0004's pinned-tree
claim.

**Acceptance criteria:**
- [ ] SC-8 verified (frozen install; stale lockfile fails the build) —
      via CI build step or documented local check cited in the PR;
      Traceability updated
- [ ] No new ADR (reality now matches what ADR 0004 already records)

---

## Wrap-up (with the last task's PR or its own tiny PR)

- [ ] Every criterion in the spec's Traceability table maps to a
      passing test; coverage check green in CI
- [ ] Spec and plan statuses → `Implemented` (freeze)
- [ ] Rebuild the live `opn-mcp` image once (rollout step from
      plan.md); MCP client config unchanged
