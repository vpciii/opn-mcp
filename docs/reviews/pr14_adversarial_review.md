# Adversarial PR Review: PR #14 ("fix: sync scheduled-task templates with their live skills")

A review of the changes in PR #14 submitted to address the findings identified during the adversarial review of PR #13.

---

## 1. Resolution of Critical Document Drift
> [!TIP]
> **Status:** FULLY RESOLVED

PR #14 synchronized the templates in `docs/scheduled-tasks/` with the active skill instructions in `scheduled-tasks/` (commit [bb54f6f](file:///Users/vpciii/Developer/personal/opn-mcp/docs/reviews/pr13_adversarial_review.md)).
* Both [docs/scheduled-tasks/daily-summary.md](file:///Users/vpciii/Developer/personal/opn-mcp/docs/scheduled-tasks/daily-summary.md) and [docs/scheduled-tasks/security-check.md](file:///Users/vpciii/Developer/personal/opn-mcp/docs/scheduled-tasks/security-check.md) now contain the complete set of instructions, including the daily firmware refresh check (Step 0) and the synthetic status checks (WireGuard, gateway status, swap pressure).
* This eliminates the risk of operators copying stale/broken prompts when following the monitoring guide in [docs/MONITORING.md](file:///Users/vpciii/Developer/personal/opn-mcp/docs/MONITORING.md), resolving the artifact honesty defect.

---

## 2. Verification of the `refresh` Parameter Trigger Path
> [!TIP]
> **Status:** FULLY RESOLVED

PR #14 added two unit tests in [tests/test_updates_available.py](file:///Users/vpciii/Developer/personal/opn-mcp/tests/test_updates_available.py) (commit [acba5c9](file:///Users/vpciii/Developer/personal/opn-mcp/docs/reviews/pr13_adversarial_review.md)):
1. `test_refresh_triggers_a_firmware_check_before_reading_status` verified that `refresh=True` executes a `POST` request to `/api/core/firmware/check` (mocking the `asyncio.sleep` to run instantaneously).
2. `test_default_does_not_trigger_a_firmware_check` verified that standard read calls do not send POST requests, safeguarding OPNsense package mirror bandwidth.

The unit tests run successfully, ensuring that CI now guards the firmware refresh trigger behavior.

---

## 3. Remaining / Outstanding Findings (Follow-ups)

### Timezone Coupling in Daily Summary Polling
* **Status:** OUTSTANDING (Synchronized to both files)
* **Location:** [docs/scheduled-tasks/daily-summary.md:L23](file:///Users/vpciii/Developer/personal/opn-mcp/docs/scheduled-tasks/daily-summary.md#L23) and [scheduled-tasks/opnsense-daily-summary/SKILL.md:L23](file:///Users/vpciii/Developer/personal/opn-mcp/scheduled-tasks/opnsense-daily-summary/SKILL.md#L23)
* **Issue:** The daily summary agent still expects the OPNsense `last_check` timestamp to contain "today's date in America/New_York". If the firewall is set to a different timezone (e.g. UTC, Asia/Tokyo, or NZST), the dates will mismatch at the 8:00 AM check window, causing the agent's poll loop to fail and report false warnings.
* **Suggested Fix:** Change the instruction to compare against today's date in the *firewall's* configured timezone (retrieved via the `last_check` string or another system API) or relax the match to check if the timestamp is within the last 15 minutes instead of string-matching a static calendar date.

### Alerting Exclusions for Removals and Reinstalls
* **Status:** OUTSTANDING (Hunch)
* **Location:** [server.py:L799](file:///Users/vpciii/Developer/personal/opn-mcp/server.py#L799)
* **Issue:** The update status continues to ignore `remove_packages` and `reinstall_packages`. While these are visible in `package_counts`, they do not trigger `updates_available = True`.

---

## Verdict: NO STRONG OBJECTION

PR #14 successfully resolved the block-level documentation drift and test theater defects identified in the PR #13 review. The timezone coupling remains a minor logical limitation that should be addressed as a task-level improvement rather than a merge block.
