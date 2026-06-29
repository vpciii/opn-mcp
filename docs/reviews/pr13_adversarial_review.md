# Adversarial PR Review: PR #13 ("fix: stale / inverted OPNsense update detection")

A retrospective review of the merged changes in PR #13, analyzing correctness, test coverage, and documentation integrity against the project guidelines.

---

## 1. Critical Finding: Document Drift & Template Stale-out
> [!IMPORTANT]
> **Status:** DEFECT / CONTRACT VIOLATION
> **Class:** Block-level finding (to be resolved via a follow-up PR)

The PR updated the active task instructions in the following files:
- [scheduled-tasks/opnsense-daily-summary/SKILL.md](https://github.com/vpciii/opn-mcp/blob/main/scheduled-tasks/opnsense-daily-summary/SKILL.md)
- [scheduled-tasks/opnsense-security-check/SKILL.md](https://github.com/vpciii/opn-mcp/blob/main/scheduled-tasks/opnsense-security-check/SKILL.md)

However, it failed to update the corresponding template files in `docs/scheduled-tasks/`:
- [docs/scheduled-tasks/daily-summary.md](https://github.com/vpciii/opn-mcp/blob/main/docs/scheduled-tasks/daily-summary.md)
- [docs/scheduled-tasks/security-check.md](https://github.com/vpciii/opn-mcp/blob/main/docs/scheduled-tasks/security-check.md)

### Impact
The setup guide at [docs/MONITORING.md#L157](https://github.com/vpciii/opn-mcp/blob/main/docs/MONITORING.md#L157) and [docs/MONITORING.md#L165](https://github.com/vpciii/opn-mcp/blob/main/docs/MONITORING.md#L165) explicitly directs users to copy their scheduled tasks from those files:
> **Prompt**: see [scheduled-tasks/daily-summary.md](scheduled-tasks/daily-summary.md)

Because the templates were not updated, any operator setting up the project following [docs/MONITORING.md](https://github.com/vpciii/opn-mcp/blob/main/docs/MONITORING.md) will copy obsolete prompts. The copied prompts:
1. **Lack the daily refresh step (Step 0)**, which means the OPNsense update alerts will continue to go stale (the exact bug PR #13 claimed to fix).
2. **Lack the WireGuard, gateway, and memory pressure checks** added in other updates, resulting in silent monitoring failures.

This violates the hard rule in [CLAUDE.md#L54](https://github.com/vpciii/opn-mcp/blob/main/CLAUDE.md#L54):
> Docs change in the same PR as the behavior.

---

## 2. Timezone Coupling Bug in Polling Logic
> [!WARNING]
> **Status:** UNSTATED CASE / DEFECT
> **Class:** Logic Flaw

In [scheduled-tasks/opnsense-daily-summary/SKILL.md:L23](https://github.com/vpciii/opn-mcp/blob/main/scheduled-tasks/opnsense-daily-summary/SKILL.md#L23), the agent is instructed to poll the `/core/firmware/status` cache:
> until its `last_check` string contains **today's** date in America/New_York (e.g. `Sat Jun 20 ... 2026`).

### Impact
1. **Firewall Timezone Offset:** If the OPNsense firewall is configured in a timezone ahead of America/New_York (e.g., UTC, Asia/Tokyo, or Pacific/Auckland), then at the 8:00 AM America/New_York check time, the firewall's clock may have already crossed into the next calendar day.
   - For example, if the firewall is in New Zealand (NZST, UTC+12), 8:00 AM EDT on June 20 is 12:00 AM NZST on June 21. The completed check output on the firewall will read `Sun Jun 21 ...`.
   - The runner (checking for `"Jun 20"`) will fail to match this date, poll 5 times (~2 minutes), and then terminate with the warning `"firmware check did not refresh in time — update counts may be stale"`.
2. **Locale Dependency:** The output of OPNsense's `last_check` string depends on the FreeBSD `date` format and system locale. If the system is set to a non-English locale, the string might not contain `"Sat"` or `"Jun"`, causing the match to fail regardless of the timezone.

---

## 3. Test Theatre: Untested `refresh` Parameter & Agent Paths
> [!NOTE]
> **Status:** TEST COVERAGE GAP
> **Class:** CI Blind Spot

1. **`refresh` logic is not covered:** While the regression tests in [tests/test_updates_available.py](https://github.com/vpciii/opn-mcp/blob/main/tests/test_updates_available.py) verify the boolean inversion for `updates_available`, they never pass `refresh=True` to [get_updates_available](https://github.com/vpciii/opn-mcp/blob/main/server.py#L765). The async trigger code:
   ```python
   await _post("/core/firmware/check")
   await asyncio.sleep(3)
   ```
   at [server.py:L774-783](https://github.com/vpciii/opn-mcp/blob/main/server.py#L774-783) goes completely unasserted.
2. **Agent logic has zero CI coverage:** The test suite verifies the FastMCP server, but has no tests for the actual scheduled task behavior (the polling loop, parsing results, and issuing notifications). This lack of test automation allowed the timezone bug and the document drift to pass CI unnoticed.

---

## 4. Unstated Case: Ignored Package Removals and Reinstalls
> [!NOTE]
> **Status:** HUNCH
> **Class:** Feature Limitation

The update status check in both [get_updates_available](https://github.com/vpciii/opn-mcp/blob/main/server.py#L799) and [get_security_digest](https://github.com/vpciii/opn-mcp/blob/main/server.py#L1116-1118) derives `updates_available` purely from `upgrade_packages` and `new_packages`:
```python
"updates_available": len(upgrade_packages) + len(new_packages) > 0,
```
If a system has pending removals (`remove_packages`) or reinstalls (`reinstall_packages`) but no new/upgraded packages:
1. `updates_available` will evaluate to `False`.
2. No notification will be sent, meaning a firewall requiring package cleanups (due to deprecations or conflicts) will report clean.

---

## Verdict: BLOCK

### Reason
Although the core python fix for the inverted boolean is correct and verified by a red-to-green test, the PR violated the project's Definition of Done and documentation rules by failing to update the user-facing scheduled task templates in [docs/scheduled-tasks/](https://github.com/vpciii/opn-mcp/blob/main/docs/scheduled-tasks/), directly resulting in broken setups for any new user. A follow-up PR is required to synchronize the documentation and address the timezone coupling in the daily summary task.
