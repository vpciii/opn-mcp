# Hands-off security monitoring

This guide turns `opn-mcp`'s `get_security_digest` tool into autonomous monitoring: a scheduled Claude Code agent runs the digest on a cron, classifies findings by severity, and pushes notifications to the Home Assistant mobile app — silent on a clean system, immediate on real signal, deferred to morning for low-priority noise.

The end state: you stop checking the firewall manually. Your phone tells you when something genuinely matters, and only then.

---

## Architecture

```
┌─────────────────────────┐
│ Claude Code scheduled   │  cron: 0 * * * *    (security-check, hourly)
│ task (background agent) │  cron: 0 8 * * *    (daily-summary, 8 AM)
└────────┬────────────────┘
         │
         │ 1. call get_security_digest
         ▼
┌─────────────────────────┐
│ opn-mcp (this repo)     │  Docker stdio MCP server
│ → OPNsense API          │
└────────┬────────────────┘
         │
         │ 2. classify warnings (HIGH / MEDIUM / LOW)
         │ 3. apply quiet hours (LOW deferred 23:00–08:00)
         │ 4. compose short push + full persistent message
         ▼
┌─────────────────────────┐
│ ha-mcp                  │  Home Assistant MCP server
│ → ha_call_service       │
└────────┬────────────────┘
         │
         │ notify.notify         → push to all linked HA mobile apps
         │ persistent_notification.create → bell icon in HA UI
         ▼
                      📱 phone push          🔔 HA bell icon
              (lock-screen readable)    (full markdown, persists)
```

Two notifications per fired alert:
- **Push**: one dense line, designed to be read fully on the lock screen. Has a `tag` so successive pushes with the same tag replace rather than stack.
- **Persistent**: full multi-line markdown, lives in HA's bell icon until you dismiss it. Stable `notification_id` per task, so the next run replaces the prior — no clutter, always shows the current state.

---

## Severity tiers

The scheduled task classifies each warning emitted by `get_security_digest` into one of three tiers. The tier determines whether to notify and when.

### HIGH — notify any time, 24/7

Active attack or breakage signals. Wake the user.

- Any failed UI login attempts (any count)
- Any denied configd admin actions
- Any service reported as not running
- Any cert flagged as expired-and-in-use
- Any cert with `days_until_expiry < 7`
- WAN-origin firewall blocks ≥ 200 in window (real flood)
- pf state table at `critical` (≥ 90% full)

### MEDIUM — notify any time, 24/7

Needs attention; not on fire.

- Cert with `7 ≤ days_until_expiry < 30`
- WAN-origin firewall blocks 100–199 in window
- pf state table at `high` (70–90% full)

### LOW — notify only between 08:00 and 23:00 local

Informational; can wait until morning.

- Pending OPNsense / package updates
- WAN-origin firewall blocks 50–99 in window (low-grade noise)
- Anything else not matched above

If a run produces only LOW warnings outside waking hours, the task exits silently. The next run after 08:00 will pick them up.

If any HIGH or MEDIUM warning is present, the task fires immediately regardless of the hour.

---

## Prerequisites

Before creating the scheduled tasks, verify the foundation:

### 1. `opn-mcp` is **user-scoped**, not project-scoped

Scheduled Claude Code tasks run in a fresh session that doesn't inherit project-scoped MCP servers. Check with:

```bash
claude mcp get opnsense
# Should report: Scope: User config (available in all your projects)
# Status: ✓ Connected
```

If it shows `Scope: Local config (private to you in this project)`, move it. The fastest way is to edit `~/.claude.json` directly: cut the `opnsense` entry from `projects.<your-project-path>.mcpServers` and paste it into the top-level `mcpServers` object.

### 2. The Docker invocation includes `--init` and **does not** include `--name`

```jsonc
"opnsense": {
  "command": "/usr/local/bin/docker",
  "args": [
    "run", "-i", "--rm", "--init",
    "-e", "OPNSENSE_HOST=...",
    "-e", "OPNSENSE_API_KEY=...",
    "-e", "OPNSENSE_API_SECRET=...",
    "-e", "OPNSENSE_VERIFY_SSL=true",
    "opn-mcp"
  ]
}
```

- `--init` runs `tini` as PID 1 inside the container. Without it, when the parent task closes stdin, signals don't propagate cleanly to the python process and the container hangs around indefinitely (`--rm` only fires on exit).
- Omit `--name` from the args. With a fixed name, concurrent task runs collide on docker's name uniqueness rule and fail.

### 3. Home Assistant MCP is reachable from scheduled-task context

The scheduled task calls `mcp__Home_Assistant__ha_call_service`. Make sure your HA MCP entry is in user scope too — same logic as `opn-mcp`.

If your HA setup uses Claude Desktop's config (`~/Library/Application Support/Claude/claude_desktop_config.json`) instead of Claude Code's, scheduled tasks won't see it. Either replicate the entry into `~/.claude.json` user scope, or rely on Claude Desktop only.

### 4. Permission allow-list

Without pre-approval, every scheduled run prompts for tool approval — defeating the autonomy. Add to `~/.claude/settings.local.json`:

```json
{
  "permissions": {
    "allow": [
      "mcp__opnsense__get_security_digest",
      "mcp__Home_Assistant__ha_call_service"
    ]
  }
}
```

Note: `ha_call_service` is generic — it can call any HA service. If that scope feels too broad for autonomous use, switch to a specific notify entity (e.g., `notify.your_iphone`) and adjust the task prompts accordingly.

---

## The scheduled tasks

Two tasks. Both are Claude Code routines stored in `~/.claude/scheduled-tasks/<taskId>/SKILL.md` (created via `mcp__scheduled-tasks__create_scheduled_task`).

### `opnsense-security-check` — hourly

Cron: `0 * * * *` (local time). Initially set to every 30 minutes, then dialed back to hourly after living with it surfaced more LOW-severity noise than useful signal — see the tuning notes below.

**Behavior**: silent on a clean digest. Notify only when `warnings` is non-empty AND severity rules permit (LOW warnings are deferred outside 08:00–23:00).

**Prompt**: see [scheduled-tasks/security-check.md](scheduled-tasks/security-check.md).

### `opnsense-daily-summary` — daily at 08:00

Cron: `0 8 * * *` (local time).

**Behavior**: heartbeat. Always sends a notification regardless of whether warnings are present. Confirms monitoring is alive and gives a 24-hour roll-up of stats.

**Prompt**: see [scheduled-tasks/daily-summary.md](scheduled-tasks/daily-summary.md).

The daily summary is intentionally redundant with the 30-minute check during anomalies — same warnings, just summarized once a day. The point isn't novel information; it's the silence-as-failure-mode problem. If a check task silently breaks (MCP down, credentials expired, network gone), you wouldn't know unless something explicitly fires every day.

---

## Creating the tasks

If you have the `mcp__scheduled-tasks` MCP server set up, you can create them via Claude:

```
Use mcp__scheduled-tasks__create_scheduled_task with:
- taskId: opnsense-security-check
- cronExpression: 0 * * * *
- description: Run get_security_digest hourly and push HA mobile notifications for warnings, with severity-tiered quiet hours.
- prompt: <copy from docs/scheduled-tasks/security-check.md>
```

And similarly for `opnsense-daily-summary` with `cronExpression: 0 8 * * *`.

Or copy the prompts straight into `~/.claude/scheduled-tasks/<taskId>/SKILL.md` files manually — see the scheduled-tasks MCP docs for the exact frontmatter format.

---

## Pre-approve the tools (one-time setup)

The first time a scheduled task tries to call an MCP tool, Claude Code prompts for approval. You want to pre-approve so the cron runs are truly hands-off.

1. From the **Scheduled** sidebar in Claude Code, click **Run now** on `opnsense-daily-summary`.
2. Approve `mcp__opnsense__get_security_digest` and `mcp__Home_Assistant__ha_call_service` when prompted.
3. Once these are in `permissions.allow` (see prerequisite 4 above), future runs won't prompt.
4. Verify a notification arrives on your phone with the daily summary.

If the test run reports `The mcp__opnsense__get_security_digest tool isn't available in this session — the OPNsense MCP server isn't connected`, the user-scope move from prerequisite 1 didn't take. Check `claude mcp get opnsense` again.

---

## Tuning notes

The thresholds picked here suit a single-user home network. Adjust to taste:

| Threshold | Default | Tune up if… | Tune down if… |
|---|---|---|---|
| WAN-block LOW floor | 50 | You're getting LOW alerts on baseline internet noise. Raise to 100–150. | You want earlier visibility into reconnaissance. |
| WAN-block HIGH floor | 200 | Your firewall normally sees high block volume. | Even modest scans should wake you up. |
| Cert near-expiry | 30 days | Renewals are reliable. | You need more buffer to investigate failures. |
| pf state HIGH | 70% | Lots of legitimate concurrent connections. | Want earlier DDoS warning. |
| Quiet hours | 23:00–08:00 | You sleep different hours. | (Same — just shift the bounds.) |

Severity classification lives in the task prompts (`docs/scheduled-tasks/*.md`). To change a tier, edit the prompt and update the scheduled task via `mcp__scheduled-tasks__update_scheduled_task`.

---

## Troubleshooting

### Containers piling up

If `docker ps --filter ancestor=opn-mcp` shows multiple auto-named containers (e.g. `competent_goldstine`, `vigilant_pasteur`) hanging around for tens of minutes, the `--init` flag is missing or the python process isn't exiting cleanly on stdin EOF.

- Verify `--init` is in the docker args (see prerequisite 2).
- Restart Claude Code so its main session respawns the container with the new args.
- Quick cleanup that won't touch your long-running named containers:
  ```bash
  docker rm -f $(docker ps -a --filter ancestor=opn-mcp \
    --format '{{.ID}} {{.Names}}' \
    | awk '$2 != "opn-mcp" && $2 != "opn-mcp-claude" {print $1}')
  ```

### Notification arrives but you can't read the full text

Mobile lock screens hard-truncate notifications. The push is intentionally a single dense line for that reason. To read the full message:

- **iOS**: long-press / hard-press the notification on the lock screen to expand. Or pull down from the top of the phone for the Notification Center, where the full body text is visible.
- **Android**: pull down with two fingers on the notification, or tap the chevron.
- Once you tap the notification, it disappears from the lock screen. Read the **persistent_notification** version inside HA — bell icon at the top right of the dashboard. The persistent version has the same data but in full markdown formatting, and stays until you dismiss it.

### Notification doesn't arrive at all

Run the daily summary manually from the Scheduled sidebar. Check the task's reported output. Common failure modes:

- *"OPNsense MCP server isn't connected"* → user-scope problem, see prerequisite 1
- *"ha_call_service not available"* → HA MCP not user-scoped
- *Tool approval prompt loops every run* → permission allow-list missing, see prerequisite 4
- *Task ran successfully but no phone push* → check `notify.notify` is configured to forward to your mobile app in HA's `configuration.yaml`. The HA Companion App must be installed and signed in.

### `notify.notify` group vs specific device

`notify.notify` is HA's default group service that fans out to all configured notify targets. If you only want to notify a specific device, replace `notify.notify` in the task prompts with the target entity (e.g., `notify.matt_s_iphone`) and re-narrow the permission allow-list accordingly.

---

## What this doesn't cover

- **De-duplication across runs** — each 30-minute check is independent. A sustained warning produces a notification every cycle. The `tag` field on the push collapses successive pushes (newer replaces older on the lock screen), so you don't get a wall of repeats — but each run still posts. If the noise becomes unbearable, add a state file (e.g., `/tmp/opnsense-last-warnings-hash`) and skip notifications when the warning set is unchanged from last run.
- **WAN attacks targeting a specific port** — the digest's WAN-block aggregation surfaces top source IPs and destination ports, but doesn't alert on patterns (e.g., 50 attempts on port 22 over 10 minutes). For pattern detection, you'd want a real SIEM or to layer Suricata IDS on top.
- **Outbound exfiltration** — `get_top_talkers` provides the data but the digest doesn't classify exfil patterns. A sustained ≥10 MB/s upload from a non-server LAN device is a candidate signal you'd add as a custom check.

These are good Pass 4+ candidates if you want to extend further.
