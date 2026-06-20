# ADR 0008: Single-source the scheduled-task prompts

- **Status:** Accepted
- **Date:** 2026-06-20
- **Deciders:** Vince Ciganik

## Context

Each scheduled-task prompt lived in **two** tracked copies:

- `scheduled-tasks/<id>/SKILL.md` — the version-controlled mirror of the
  routines that actually run (deployed under
  `~/.claude/scheduled-tasks/<id>/SKILL.md`).
- `docs/scheduled-tasks/<id>.md` — a copy-paste "template" that
  `docs/MONITORING.md` directed new operators to.

The second copy was introduced without any mechanism to keep it in step
with the first. Updates landed on the skill only; the template drifted.
By the time of PR #13's "refresh the firmware check first" fix, the
template was missing that step (and the WireGuard/gateway/memory/DNS
checks added earlier), so an operator following the setup guide copied a
stale prompt that recreated the very stale-"no updates" bug PR #13 fixed.

A cross-model adversarial review of PR #13 caught it (`docs/reviews/`);
PR #14 re-synced the templates by hand as a stop-gap. But re-syncing only
resets the clock — two hand-maintained copies of one prompt drift again.
The global methodology now names this directly: a fact lives in one place,
and an unavoidable second copy is generated or machine-checked, never
synced by memory (methodology ADR 0022). The durable fix is to stop
duplicating.

## Decision

**The `scheduled-tasks/<id>/SKILL.md` files are the single source of each
task prompt.** They mirror what actually runs, so documentation derives
from them, not the reverse.

- **Delete `docs/scheduled-tasks/`.** There is no second copy of the
  prompt body to drift.
- **`docs/MONITORING.md` references the skill directly** — the prompt to
  paste is the body of `scheduled-tasks/<id>/SKILL.md` (everything below
  the frontmatter). The setup-only settings that are *not* part of the
  prompt (cron, taskId, description, `notifyOnCompletion`) stay in
  MONITORING.md, where the rest of the setup already lives.

This supersedes PR #14's manual re-sync; that PR's durable value — the
`refresh` regression tests and the review record — stands.

## Alternatives considered

- **Generate the templates from the skills + a CI equality check** —
  keeps a self-contained copy-paste block and is methodology-legal (a
  generated/checked copy, ADR 0022). Rejected: it adds a generator script
  and a CI step to maintain for two files whose content already lives one
  directory away. Single-sourcing by *removal* is simpler than
  single-sourcing by *generation* when the duplicate need not exist.
- **Keep both copies, re-sync by hand (status quo + PR #14)** — rejected:
  this is exactly the memory-synced duplication methodology ADR 0022 names
  as the hazard. It drifts again on the next edit.
- **Make the skills generated from the docs templates** (reverse the
  canonical direction) — rejected: the skills are the operational truth;
  the docs are the derived view.

## Consequences

- Drift is impossible: one copy.
- Setup changes by one step — operators copy the prompt from the
  clearly-named `SKILL.md` instead of a docs template; the settings they
  also need remain in MONITORING.md.
- The `docs/reviews/` records that reference the deleted templates stay as
  historical record (they describe the state at review time).

## Adoption impact

None — single-user repo. The next time the tasks are set up, the operator
follows MONITORING.md's pointer to the skill body. Forward-only.

## References

- methodology ADR 0022 (single source of truth — the principle this
  applies).
- `docs/reviews/pr13_adversarial_review.md` (the drift finding),
  `docs/reviews/pr14_adversarial_review.md` (re-sync confirmed), PR #14
  (the stop-gap), `docs/MONITORING.md`.
