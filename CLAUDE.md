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
2. `docs/glossary.md` — this project's ubiquitous language. Use these
   terms exactly.
3. `docs/adr/` — every numbered ADR is binding unless `superseded`.
   Newest first.
4. The `specs/<feature>/` folder for the work at hand, if one was named.

## Hard rules

- **No code without a spec for non-trivial work.** Larger than a single
  function or bugfix → draft `specs/<slug>/spec.md` first and confirm
  before implementing. Templates: `$METHODOLOGY_HOME/templates/spec/`.
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
  commit) cited in the PR. Test behavior, not implementation.
- **Secrets never in the repo.** Env or secret manager only. Trust
  boundaries / authz are ADR-worthy; security bugs ship a regression
  test.
- **Dependencies are decisions.** Weigh maintenance/license/supply-chain
  before adding; commit lockfiles; ADR non-trivial deps.
- **Docs change in the same PR as the behavior.** Conventional Commits
  (`feat: fix: docs: refactor: test: chore: perf: build: ci:`; `!` for
  breaking).

<!-- Add project-specific hard rules below, each backed by an ADR.
     e.g. "Never represent money as a float — see ADR 0004." -->

## What this file is not

A pointer, not the methodology. If something here contradicts
`$METHODOLOGY_HOME/methodology.md` or a project ADR, the ADR wins and
this file should be updated.
