# Working notes for AI agents in this repo

This file orients an AI coding agent for **opn-mcp** — an MCP server
that exposes read-only (and a few narrow write) tools for monitoring
an OPNsense firewall. It is intentionally short. The global practices
live in `$METHODOLOGY_HOME/methodology.md` (default
`~/Developer/methodology`); the durable project-specific rules live
in `docs/adr/` and `docs/glossary.md`.

## Read first, every session

1. `$METHODOLOGY_HOME/methodology.md` — the practices and why (global;
   read once if unfamiliar, and see its "Using this methodology"
   section for the decision guide and agent operating rules).
2. `docs/architecture.md` — the current shape of the system
   (components, boundaries, stores, external deps); the ADRs say *why*.
3. `docs/glossary.md` — this project's ubiquitous language. Use these
   terms exactly.
4. `docs/adr/` — every numbered ADR is binding unless `superseded`.
   Newest first.
5. The `planning/<feature>/` folder, if the work began as a planned bet
   (`$METHODOLOGY_HOME/planning.md`).
6. The `specs/<feature>/` folder for the work at hand, if one was named.

## Hard rules

- **No code without a spec for non-trivial work.** Larger than a single
  function or bugfix → draft `specs/<slug>/spec.md` first and confirm
  before implementing. Templates: `$METHODOLOGY_HOME/templates/spec/`. For
  an uncertain or expensive bet, plan it first in `planning/<slug>/`
  (`$METHODOLOGY_HOME/planning.md`) — it converges to the spec.
- **Never invent a domain term.** If a concept needs a name and it
  isn't in `docs/glossary.md`, stop and propose it.
- **Decisions get ADRs** — expensive to reverse, multi-component, or
  future-constraining. Template: `$METHODOLOGY_HOME/templates/adr/_template.md`.
- **One PR-sized change per task.** Split past ~300 lines of diff.
- **Reversible by default.** Prefer flags / expand-contract migrations
  / backward-compatible APIs; call out and ADR anything truly
  irreversible.
- **Tests before merge.** New behavior ships with tests; bug fixes ship
  a regression test, with the failing-before run (or a test-first
  commit) cited in the PR. Test behavior, not implementation. A test that
  verifies a spec success criterion cites its id; criteria carry stable
  ids, CI-checked for coverage.
- **Specs freeze; keep the shape doc honest.** A spec freezes at
  `Implemented` (a historical record) — a contradiction found later
  goes to a test, a new spec, or an ADR, not back into it. Update
  `docs/architecture.md` in the same PR as any structural change.
- **Secrets never in the repo.** Env or secret manager only. Trust
  boundaries / authz are ADR-worthy; security bugs ship a regression
  test.
- **Dependencies are decisions.** Weigh maintenance/license/supply-chain
  before adding; commit lockfiles; ADR non-trivial deps.
- **Docs change in the same PR as the behavior.** Conventional Commits
  (`feat: fix: docs: refactor: test: chore: perf: build: ci:`; `!` for
  breaking).
- **Don't silently rewrite an agreed contract.** An `Approved` /
  `Implemented` spec's requirements and success criteria are the
  contract — a change to them is its own diff for human sign-off, never
  folded into an implementation PR. Show "done" by citing the passing
  test; re-read a spec/ADR/glossary before editing it; surface drift
  you notice.

<!-- Add project-specific hard rules below, each backed by an ADR.
     e.g. "Never represent money as a float — see ADR 0004." -->

## What this file is not

A pointer, not the methodology. If something here contradicts
`$METHODOLOGY_HOME/methodology.md` or a project ADR, the ADR wins and
this file should be updated.
