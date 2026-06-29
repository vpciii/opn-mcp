# Adversarial Review: PR #15 — Single-source Scheduled-Task Prompts (ADR 0008)

- **Status:** Complete
- **Verdict:** **PUSH BACK**
- **Date:** 2026-06-20
- **Reviewer:** Antigravity (Adversarial Persona)

---

## Executive Summary

PR #15 (implementing [ADR 0008](https://github.com/vpciii/opn-mcp/blob/main/docs/adr/0008-single-source-scheduled-task-prompts.md)) resolves the immediate issue of prompt drift by deleting the templates in `docs/scheduled-tasks/` and referencing `scheduled-tasks/<id>/SKILL.md` directly. While this technically satisfies the "single source of truth" principle, it does so by **degrading the operator setup UX**, introduces **copy-paste error vectors**, and **drops metadata settings** for one of the tasks. 

A "generate + CI check" approach would have satisfied the methodology constraints of [ADR 0022](https://github.com/vpciii/methodology/blob/main/adr/0022-single-source-of-truth.md) without sacrificing user experience.

---

## Detailed Findings

### 1. Steelman Alternative: "Generate + CI Check" vs. Removal
* **File & Line:** [docs/adr/0008-single-source-scheduled-task-prompts.md#L51-L56](https://github.com/vpciii/opn-mcp/blob/main/docs/adr/0008-single-source-scheduled-task-prompts.md#L51-L56)
* **Analysis:** The ADR rejects the "generate templates + CI check" alternative as adding "machinery for a duplicate that needn't exist." This is a false trade-off. 
  - **Setup UX Degradation:** Previously, the templates (e.g., [docs/scheduled-tasks/security-check.md](https://github.com/vpciii/opn-mcp/blob/main/docs/scheduled-tasks/security-check.md) at `HEAD~1`) wrapped the prompts in markdown code blocks (` ``` `). This rendered a clean, one-click "Copy" button in GitHub or any markdown editor. Now, the prompt is raw text in [scheduled-tasks/opnsense-security-check/SKILL.md](https://github.com/vpciii/opn-mcp/blob/main/scheduled-tasks/opnsense-security-check/SKILL.md). There is no single copy-paste container; the operator must manually select lines 5 to 184.
  - **Error Proneness:** The operator is instructed to copy "everything below the `---` frontmatter" ([docs/MONITORING.md#L157](https://github.com/vpciii/opn-mcp/blob/main/docs/MONITORING.md#L157)). If they accidentally copy the second `---` delimiter or any frontmatter lines, passing them to `mcp__scheduled-tasks__create_scheduled_task` will create a malformed skill file with duplicate/broken headers on the host.
  - **Verdict on Alternative:** The decision traded setup UX for file-count minimalism. A CI checker script that verified the templates matched the skill bodies (minus frontmatter) would have prevented drift *and* preserved the clean copy-paste container.

### 2. Lost Value and Dropped Settings
* **File & Line:** [docs/MONITORING.md#L184](https://github.com/vpciii/opn-mcp/blob/main/docs/MONITORING.md#L184)
* **Analysis:** The deleted `docs/scheduled-tasks/daily-summary.md` template explicitly documented suggested settings like:
  - `taskId`: `opnsense-daily-summary`
  - `cronExpression`: `0 8 * * *`
  - `description`: `Daily 8am OPNsense health summary push notification — heartbeat that monitoring is alive plus 24h roll-up.`
  - `notifyOnCompletion`: `false` (with rationale)
  In the updated [docs/MONITORING.md#L184](https://github.com/vpciii/opn-mcp/blob/main/docs/MONITORING.md#L184), the daily summary task creation is glossed over:
  > *"And similarly for `opnsense-daily-summary` with `cronExpression: 0 8 * * *` (prompt: the body of `scheduled-tasks/opnsense-daily-summary/SKILL.md`)."*
  - The `description` value is completely dropped from the documentation. While it exists in the skill's YAML frontmatter, the operator is told to copy only *below* the frontmatter, creating a risk that they create the task without a description.
  - The `notifyOnCompletion` parameter is not explicitly defined for `opnsense-daily-summary`, leaving the user to assume "similarly" maps to the hourly task's setup.

### 3. Canonical Direction: Skill vs. Template
* **Analysis:** The ADR asserts `scheduled-tasks/<id>/SKILL.md` is the operational source of truth. This is correct: a skill is what is executed, and its structure is governed by Claude Code's skill requirements (including YAML frontmatter). Documenting the runtime file as canonical is correct. However, this does not justify exposing the raw runtime file directly to the setup process as the *sole copy-paste interface*. Exposing raw, metadata-prefixed files directly to users instead of generating a clean user-facing distribution is a failure of packaging.

### 4. Consistency with Citing Rule (ADR 0022)
* **File & Line:** [methodology/adr/0022-single-source-of-truth.md](https://github.com/vpciii/methodology/blob/main/adr/0022-single-source-of-truth.md)
* **Analysis:** The decision claims to satisfy global [ADR 0022](https://github.com/vpciii/methodology/blob/main/adr/0022-single-source-of-truth.md). However, ADR 0022 explicitly states:
  > *"If it must exist in more than one — a generated artifact, a mirrored summary, a copy some tool requires — the copy is **generated from** the source or **machine-checked against** it, **never kept in sync by human memory**..."*
  - Therefore, a check script in CI would have been 100% compliant with ADR 0022. 
  - Removal is described in ADR 0022 as the "cheapest correct response," which the author of ADR 0008 used as a preference to avoid implementing the checker logic. This was a developer-convenience preference rather than a strict methodology constraint.

### 5. Broken or Stale References
* **README:** [README.md#L133](https://github.com/vpciii/opn-mcp/blob/main/README.md#L133)
  - The file still says: `scheduled-task prompt templates`. Since the templates were deleted, this reference is stale. It should refer to `scheduled-task prompts` or `scheduled-task skill bodies`.
* **Historical review records:** [docs/reviews/pr13_adversarial_review.md](https://github.com/vpciii/opn-mcp/blob/main/docs/reviews/pr13_adversarial_review.md) and [docs/reviews/pr14_adversarial_review.md](https://github.com/vpciii/opn-mcp/blob/main/docs/reviews/pr14_adversarial_review.md) reference the deleted files. This is acceptable as historical context, but it means readers of old reviews will hit broken links.

---

## Verdict & Recommendation

**PUSH BACK**

### Recommended Remediations
1. **Restore Template Generation or Verification:** Re-introduce the `docs/scheduled-tasks/*.md` template files containing clean code blocks for the prompt bodies, and add a simple python validator in `scripts/` (and `.github/workflows/ci.yml`) to verify that the template code block matches the body of the corresponding `scheduled-tasks/*/SKILL.md` (lines after the frontmatter).
2. **Fix Missing Metadata:** If removal is insisted upon, [docs/MONITORING.md](https://github.com/vpciii/opn-mcp/blob/main/docs/MONITORING.md) must be updated to fully document the `description` and `notifyOnCompletion` arguments for `opnsense-daily-summary` instead of dropping them.
3. **Update Stale Terminology:** Clean up the stale reference to "templates" in [README.md#L133](https://github.com/vpciii/opn-mcp/blob/main/README.md#L133).
