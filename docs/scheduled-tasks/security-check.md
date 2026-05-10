# `opnsense-security-check` task prompt

Template for the recurring 30-minute security check. Copy this into the `prompt` field when creating the scheduled task via `mcp__scheduled-tasks__create_scheduled_task`.

**Suggested settings:**
- `taskId`: `opnsense-security-check`
- `cronExpression`: `*/30 * * * *`
- `description`: `Run get_security_digest every 30 min and push HA mobile notifications for warnings, with severity-tiered quiet hours.`
- `notifyOnCompletion`: `false` (we don't want a session ping for every run; the actual notifications go to HA mobile)

---

```
Run a security check on the OPNsense firewall and notify if something's wrong.

This task runs every 30 minutes. It should be silent on a clean system and only notify when warnings appear, with severity-tier-based quiet hours.

Each notification has two parts:
1. A short push to the HA mobile app (one dense line, lock-screen readable)
2. A `persistent_notification` inside HA (full detail, lives in the bell icon, stays until dismissed)

## Steps

### 1. Call the digest

Call `mcp__opnsense__get_security_digest` (default window_lines=500).

### 2. If `warnings` array is empty, exit silently

Don't send any notification. Don't print anything dramatic. Just report "Clean digest — no warnings. Exiting silently as expected." and stop. The check ran clean — that's the expected case 99% of the time.

### 3. Classify each warning by severity

**HIGH** (notify any time, 24/7):
- Any "failed UI login attempt" warning (any count)
- Any "denied admin action" warning
- Any "service(s) not running" warning
- Any "Certificate ... is EXPIRED and in use" warning
- Any "Certificate ... expires in N d" where N < 7
- Any "WAN-origin firewall blocks" warning where count >= 200
- Any "pf state table" warning where percent >= 90 (critical)

**MEDIUM** (notify any time, 24/7):
- "Certificate ... expires in N d" where 7 <= N < 30
- "WAN-origin firewall blocks" where 100 <= count < 200
- "pf state table" where 70 <= percent < 90

**LOW** (notify only between 08:00 and 23:00 local time):
- "Pending OPNsense / package updates"
- "WAN-origin firewall blocks" where 50 <= count < 100
- Anything else not matched above

### 4. Apply quiet hours

Get the current local time (America/New_York). If the current hour is < 8 or >= 23 AND **all** warnings are LOW severity, exit silently — they'll be picked up by the next run after 08:00.

Otherwise (any HIGH/MEDIUM, or any time during waking hours), proceed.

### 5. Build the messages

Determine the highest severity present (HIGH > MEDIUM > LOW). Pick its emoji: 🚨 / ⚠️ / ℹ️.

**Short push body** (one line, target ~80 chars, max 110):
- Format: `<emoji> <N> <SEVERITY> · <top warning condensed>`
- The "top warning condensed" picks the most important warning and summarizes in 4-7 words.
  - Failed login → `<N> failed UI logins`
  - Denied action → `<N> denied admin actions`
  - Service stopped → `service down: <names>`
  - Cert expired → `cert EXPIRED: <descr>`
  - Cert expiring → `cert <descr> in <N>d`
  - WAN blocks → `<N> WAN blocks`
  - State table → `pf state <pct>%`
  - Updates → `updates available`
- Examples:
  - `🚨 1 HIGH · 3 failed UI logins`
  - `⚠️ 2 MEDIUM · cert 12d, WAN blocks 145`
  - `ℹ️ 1 LOW · 92 WAN blocks`
- If multiple warnings, mention the count and the most-severe one.

**Push title**: `OPNsense: <SEVERITY>` (e.g., `OPNsense: HIGH`)

**Persistent (full) message** (multi-line markdown, no length cap):
- Bullet list of all warnings with severity emoji
- Then a "Context" section with the key supporting data:
  - For firewall blocks: top 3 source IPs from `info.firewall.top_blocked_sources_wan` with counts
  - For cert warnings: cert descr + exact days
  - For service warnings: list stopped services from `info.services.stopped`
  - For auth: top failed source IPs from `info.auth.top_failed_ips`

### 6. Send both notifications

**Step 6a — push to phones:**

Call `mcp__Home_Assistant__ha_call_service`:
- domain: `notify`
- service: `notify`
- data:
```
{
  "title": "<push title>",
  "message": "<short push body>",
  "data": {
    "tag": "opnsense_security_check"
  }
}
```

The `tag` makes successive pushes with the same tag *replace* the previous one on the lock screen instead of stacking — so 30-min checks don't pile up.

**Step 6b — persistent notification in HA's bell icon:**

Call `mcp__Home_Assistant__ha_call_service`:
- domain: `persistent_notification`
- service: `create`
- data:
```
{
  "notification_id": "opnsense_security_check",
  "title": "<push title>",
  "message": "<full multi-line markdown>"
}
```

Using a stable `notification_id` means each run replaces the prior persistent notification rather than building a wall of them. The latest is always the current state.

### 7. Report what happened

One sentence: warnings count, severity, whether you notified or deferred for quiet hours.

## What NOT to do

- Don't notify on a clean digest (warnings = []).
- Don't notify if all warnings are LOW and it's between 23:00 and 08:00.
- Don't try to "improve" the digest by calling other tools — keep this fast and predictable.

## Quiet-hours examples

- Run at 02:00, warnings = ["Pending updates"] → all LOW → defer, no notification
- Run at 02:00, warnings = ["3 failed UI login attempts", "Pending updates"] → HIGH present → notify (mention both)
- Run at 09:00, warnings = ["Pending updates"] → LOW outside quiet hours → notify
- Run at 09:00, warnings = [] → no warnings → silent
```
