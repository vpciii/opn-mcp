# Contributing

This project follows the shared methodology at
`$METHODOLOGY_HOME/methodology.md` — a small set of durable
practices that predate (and outlast) any particular tool or framework.
Synced to methodology 0.9.0.

## Before you write code

1. Read `$METHODOLOGY_HOME/methodology.md` (once, if unfamiliar).
2. Read `docs/architecture.md` for the current shape of the system,
   then skim `docs/adr/` from highest number down for the *why*.
3. For anything larger than a one-line fix, open or claim an issue
   first.

## How work flows

> For an **uncertain or expensive bet** — where it's not yet clear *what*
> or *whether* to build — do the pre-spec planning first in
> `planning/<slug>/` (problem, options, appetite) per
> `$METHODOLOGY_HOME/planning.md`; it converges to the spec below.
> Clear-cut work skips straight to the spec.

1. **Spec** — for any non-trivial feature, copy the spec templates
   from `$METHODOLOGY_HOME/templates/spec/` to
   `specs/<feature-slug>/` and fill in `spec.md`. Discuss in a PR
   before writing code.
2. **Plan** — once the spec is agreed, fill in `plan.md` (how) and
   `tasks.md` (PR-sized chunks).
3. **Build** — one PR per task. Trunk-based: short-lived branches,
   merged to `main` frequently. Keep PRs under ~300 lines of diff
   where you can.
4. **Decide** — write an ADR when a decision is **expensive to
   reverse**, **affects multiple components**, or **constrains
   future choices**. See `methodology.md` §1 and the template at
   `$METHODOLOGY_HOME/templates/adr/_template.md`.

## Definition of ready

**A task is ready to start when:**

- The problem and the user-visible outcome are stated (in the spec, or
  the issue for small work).
- Success criteria are concrete and testable.
- Open questions are resolved or explicitly deferred (not silently
  ignored).
- Any decision it depends on already has an ADR, or one is queued.
- It is PR-sized (or has been split until it is).

If a task can't meet this bar, it isn't ready — sharpen the spec
first rather than starting to code.

## Definition of done

**A task (one PR) is done when:**

- The PR is merged to `main`.
- All tests pass in CI.
- Lint and strict type-check pass (per the project's tooling ADR).
- The corresponding task in `tasks.md` is marked `[x]` with the
  merged PR number or hash.
- Any new behavior is covered by at least one test; a test that
  verifies a spec success criterion cites its id (methodology §5).
- A bug fix cites its **red→green evidence**: the regression test's
  failing output from before the fix, or a test-first commit a
  reviewer can check out and run (methodology §5, ADR 0015).
- No secrets were committed; any security-relevant change is covered
  by a test, and any irreversible step was called out (methodology
  §9, §11).
- Any new or upgraded dependency was weighed and recorded as needed,
  with the lockfile committed (methodology §10).
- Any new domain term used in code or tests appears in
  `docs/glossary.md` (methodology §3).
- Any significant decision made during implementation has an ADR
  (methodology §1).
- If the task resolved an incident, the operational feedback rule is
  satisfied (methodology §8): a regression test, an ADR, or a spec
  update.

**A feature (one spec) is done when:**

- Every task in its `tasks.md` is marked `[x]`.
- Every success criterion in `spec.md` is recorded in the spec's
  Traceability table against a passing test, and the
  spec-criterion-coverage check passes in CI (methodology §5) — not
  mapped by hand. (A reference checker to adapt or replace ships at
  `$METHODOLOGY_HOME/templates/ci/check-spec-coverage.py`, ADR 0017.)
- Every `MUST` / `MUST NOT` requirement in `spec.md` is reflected in at
  least one success criterion, so it inherits a test; the Traceability
  table records the `R-… → SC-… → test` chain (methodology §5, ADR 0011).
- Anything learned during implementation that contradicts the spec or
  plan has been written back into it **before** the spec is marked
  `Implemented`.
- The spec's status field is updated to `Implemented`, which
  **freezes** it into a historical record. A contradiction found later
  goes to a living artifact — a regression test, a new spec, or an ADR
  (methodology §2, §8) — not back into the frozen spec.

## Reviews

Every PR review covers either:

- **The full diff** between `main` and the PR head (`main..HEAD`), if
  this is the first review of the PR.
- **The delta since the last reviewed commit**
  (`<previous-reviewed-hash>..HEAD`), if the PR has been reviewed
  before. The previous reviewed commit hash must be cited explicitly
  in the new review comment.

AI-assisted PRs can grow quickly between review passes. Citing the
exact diff each review covers makes "what was reviewed" auditable and
prevents new changes sliding through under cover of a prior approval.

### What a review checks

Whatever the range, every review checks (methodology §5, §9, §11,
ADR 0015 — kept short on purpose):

- **Spec conformance** — the diff does what the spec/task says, and no
  more; requirements and success criteria were not quietly rewritten
  to match the code (methodology "agent guardrails").
- **Test honesty** — new behavior is covered; a bug fix shows its
  red→green evidence (below); tests assert behavior, not
  implementation, and would actually fail if the behavior broke.
- **Language** — domain terms match `docs/glossary.md` exactly; no
  invented synonyms.
- **Boundaries and reversibility** — no secrets; input validated at
  trust boundaries; anything irreversible called out.
- **Artifacts ride along** — docs, ADR, glossary, and
  `architecture.md` updates are in this PR, not promised for later.

## Commits and versioning

- [Conventional Commits](https://www.conventionalcommits.org/) for
  every commit. Use `!` (e.g. `feat!:`) for breaking changes.
- [Semantic Versioning](https://semver.org/) for releases.

### Commit type labels

| Label       | Meaning                                                         |
| ----------- | --------------------------------------------------------------- |
| `feat:`     | A new user-visible feature or capability.                       |
| `fix:`      | A bug fix.                                                      |
| `docs:`     | Documentation only (`*.md`, ADRs, specs, README/CONTRIBUTING/CLAUDE, LICENSE/NOTICE/etc.). |
| `chore:`    | Housekeeping: tooling, build config, `.gitignore`, scaffolding, dependency bumps — no behavior or doc-content change. |
| `refactor:` | Code reshuffle. No behavior change, no doc change.              |
| `test:`     | Adding or changing tests only.                                  |
| `perf:`     | A change whose primary purpose is performance.                  |
| `build:`    | Changes to the build system or external dependencies.           |
| `ci:`       | Changes to CI configuration or scripts.                         |

### Disambiguation rules

When a commit could fit two labels, apply in order:

1. **Mixed content** (code + docs) → label matching the change's
   *primary purpose*. If docs only describe the code change, `feat:`
   or `fix:` covers both.
2. **A new ADR or spec** → `docs:` (they are documentation even when
   they record a significant decision).
3. **Updating `.gitignore`, build config, project layout** → `chore:`.
4. **Root commits / initial scaffolds** → `chore:` is conventional
   even when docs-heavy. The one accepted exception to rule 2.

### Releases

- Tag each release `vX.Y.Z` (SemVer).
- Keep a human-facing `CHANGELOG.md` per
  [Keep a Changelog](https://keepachangelog.com/) — Conventional
  Commits make it cheap to draft or generate; curate it rather than
  dumping the git log.

## Tests

- New behavior ships with tests.
- Bug fixes ship with a regression test that fails before the fix and
  passes after — and the PR cites the failing run (or a test-first
  commit) as evidence, so red→green is shown, not asserted (ADR 0015).
- The full test suite must pass before merge.

## Using AI assistants

AI tools (Claude Code, Cursor, Cline, Aider, etc.) are welcome. They
read the same artifacts you do — `CLAUDE.md`, ADRs, specs, glossary.
The rule is simple: **the AI is not the author of record. You are.**
Review every diff. Run every test. Sign your commits.

Two guardrails matter most because they fail quietly (methodology
"AI-agent guardrails"):

- **An agent must not silently rewrite an agreed contract.** Changes to
  an `Approved` / `Implemented` spec's requirements or success criteria
  come as their own diff for your sign-off — never folded into an
  implementation PR.
- **An agent shows "done," it doesn't assert it.** A criterion claimed
  met cites the passing test that proves it; a fix claimed correct
  cites the regression test failing before it (red→green evidence).
