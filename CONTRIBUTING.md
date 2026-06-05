# Contributing

This project follows the shared methodology at
`$METHODOLOGY_HOME/methodology.md` — a small set of durable
practices that predate (and outlast) any particular tool or framework.

## Before you write code

1. Read `$METHODOLOGY_HOME/methodology.md` (once, if unfamiliar).
2. Skim `docs/adr/` from highest number down until you understand the
   shape of the system.
3. For anything larger than a one-line fix, open or claim an issue
   first.

## How work flows

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
- Any new behavior is covered by at least one test (methodology §5).
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
- Every success criterion in `spec.md` maps to a passing test.
- The spec's status field is updated to `Implemented`.
- Anything learned during implementation that contradicts the spec or
  plan has been written back into it, noted in a commit message.

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

## Tests

- New behavior ships with tests.
- Bug fixes ship with a regression test that fails before the fix and
  passes after.
- The full test suite must pass before merge.

## Using AI assistants

AI tools (Claude Code, Cursor, Cline, Aider, etc.) are welcome. They
read the same artifacts you do — `CLAUDE.md`, ADRs, specs, glossary.
The rule is simple: **the AI is not the author of record. You are.**
Review every diff. Run every test. Sign your commits.
