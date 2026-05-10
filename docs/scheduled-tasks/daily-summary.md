# `opnsense-daily-summary` task prompt

Template for the daily 8am heartbeat summary. Copy this into the `prompt` field when creating the scheduled task via `mcp__scheduled-tasks__create_scheduled_task`.

**Suggested settings:**
- `taskId`: `opnsense-daily-summary`
- `cronExpression`: `0 8 * * *`
- `description`: `Daily 8am OPNsense health summary push notification — heartbeat that monitoring is alive plus 24h roll-up.`
- `notifyOnCompletion`: `false` (the daily push to your phone is the user-visible signal; no need for an additional session ping)

---

```
Send a daily morning summary of the OPNsense firewall's security state. This is a heartbeat — runs every morning at 8am regardless of whether anything is wrong, so the user knows monitoring is still alive.

Each run produces two notifications:
1. A short push to the HA mobile app (one dense line, lock-screen readable)
2. A `persistent_notification` inside HA with the full breakdown (lives in the bell icon)

## Steps

### 1. Call the digest with a wider window

Call `mcp__opnsense__get_security_digest` with `window_lines=2000` (deeper than the 30-min check so daily totals are more representative).

### 2. Build a status icon and severity

Determine the highest-severity warning present (same classification as the security-check task):
- HIGH = failed logins / denied actions / stopped services / cert expired / cert <7d / WAN blocks ≥200 / pf state ≥90%
- MEDIUM = cert 7-30d / WAN blocks 100-199 / pf state 70-90%
- LOW = everything else

If no warnings: `✅ All clear`. Otherwise pick the severity emoji (🚨 / ⚠️ / ℹ️).

### 3. Build the short push body (one dense line, target ~100 chars)

Format: `<status> · <key stats inline>`

Stats to include (compact, separated by `·`):
- Logins: `<S>L / <F>fail` (S=successful_count, F=failed_count from info.auth)
- WAN: `<N>blk` (info.firewall.wan_origin_count)
- Stopped svc: only mention if > 0: `<N>svc down`
- Cert next: `cert <N>d` (soonest-expiring in_use cert; "OK" if all > 60d)
- Updates: only mention if available: `updates`

Examples:
- `✅ All clear · 18L / 0fail · 92blk · cert 89d`
- `⚠️ 2 warnings · 18L / 3fail · cert 12d · updates`
- `🚨 1 service stopped · unbound down · cert 89d`

Keep under ~110 chars total. The lock-screen banner truncates anything longer.

**Push title**: `OPNsense daily — <YYYY-MM-DD>` (use today's date in local time)

### 4. Build the full persistent-notification body (multi-line markdown, no length cap)

Format roughly:
```
<status emoji> **<status text>**

**Logins (24h)**: <successful_count> ok, <failed_count> failed
**WAN blocks**: <wan_origin_count> (LAN-side: <lan_origin_count> — state churn, ignored)
**Services**: <running> running, <stopped> stopped
**Cert next expiry**: <descr> in <N>d
**Updates**: available (N packages) | none
**pf state table**: <current> / <limit> (<pct>%)
**Config changes (window)**: <count>
```

If there are warnings, list them at the top with their severity emoji prefix.

### 5. Send both notifications

**Step 5a — push to phones:**

Call `mcp__Home_Assistant__ha_call_service`:
- domain: `notify`
- service: `notify`
- data:
```
{
  "title": "<push title>",
  "message": "<short push body>",
  "data": {
    "tag": "opnsense_daily_summary"
  }
}
```

**Step 5b — persistent notification in HA's bell icon:**

Call `mcp__Home_Assistant__ha_call_service`:
- domain: `persistent_notification`
- service: `create`
- data:
```
{
  "notification_id": "opnsense_daily_summary",
  "title": "<push title>",
  "message": "<full multi-line markdown body>"
}
```

Using a stable `notification_id` means the next morning replaces yesterday's — no clutter.

### 6. Report

One sentence: "Sent daily summary (<status>): <warning count or all clear>."

## Failure mode

If `get_security_digest` errors out (firewall unreachable, MCP down, etc.), still send a notification:
- Push: `❌ OPNsense daily check FAILED — <short reason>`
- Persistent: `Daily check failed:\n\n<full error>`
- Same `tag` / `notification_id` as the success path

Silent failures defeat the purpose of a heartbeat.

## Notes

- Always send this notification, even on a perfectly clean system — that's the heartbeat purpose. Silence would mean "is monitoring even running?"
- The push is for glance value; the persistent is for reading the full state when the user wants details.
```
