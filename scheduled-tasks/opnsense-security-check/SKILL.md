---
name: opnsense-security-check
description: Run get_security_digest hourly and push HA mobile notifications for warnings, with severity-tiered quiet hours.
---

Run a security check on the OPNsense firewall and notify if something's wrong.

This task runs hourly. It should be silent on a clean system and only notify when warnings appear, with severity-tier-based quiet hours.

Each notification has two parts:
1. A short push to the HA mobile app (one dense line, lock-screen readable)
2. A `persistent_notification` inside HA (full detail, lives in the bell icon, stays until dismissed)

## Known peers / expected traffic

- **WireGuard peer**: `54.224.141.79` — authorized site-to-site WG endpoint. UDP traffic to/from this IP is expected and has been observed getting incidentally blocked (handshake retries / state-churn / etc.), which the digest's single-source rule then misclassifies as a focused scan or active scan/brute. **Treat any "WAN blocks from single source 54.224.141.79 ..." warning as a false positive.**
- Same goes for WireGuard UDP ports (default 51820/udp) appearing as a top blocked dest port — that's the peer's traffic landing on closed/old ports, not an attacker.

## Steps

### 1. Call the digest

Call `mcp__opnsense__get_security_digest` (default window_lines=500).

### 2. If `warnings` array is empty, exit silently

Don't send any notification. Don't print anything dramatic. Just report "Clean digest — no warnings. Exiting silently as expected." and stop. The check ran clean — that's the expected case 99% of the time.

### 2a. Filter known false positives (WireGuard peer)

Before classifying, drop any warning whose text matches `WAN blocks from single source 54.224.141.79` (any variant — focused scan, active scan/brute, etc.). This is the authorized WG peer at `54.224.141.79`; its blocked-UDP noise is not an attack signal. Note this in the run report so the suppression is visible.

If filtering empties the warnings list, exit silently (same as step 2).

### 3. Classify each warning by severity

**HIGH** (notify any time, 24/7):
- Any "failed UI login attempt" warning (any count)
- Any "denied admin action" warning
- Any "service(s) not running" warning
- Any "Certificate ... is EXPIRED and in use" warning
- Any "Certificate ... expires in N d" where N < 7
- Any "WAN blocks from single source ... (active scan/brute)" warning (server emits this when one source ≥ 200 hits)
- Any "pf state table" warning where percent >= 90 (critical)

**MEDIUM** (notify any time, 24/7):
- "Certificate ... expires in N d" where 7 <= N < 30
- "WAN blocks from single source ... (focused scan)" warning (server emits this when one source ≥ 50 hits)
- "WAN-origin firewall blocks ... (distributed flood)" warning (server emits this when total ≥ 1000 with no single dominant source)
- "pf state table" where 70 <= percent < 90

**LOW** (notify only between 08:00 and 23:00 local time):
- "Pending OPNsense / package updates"
- Any other warnings not matched above

**Note on WAN-block suppression**: the server only emits WAN-block warnings when there's a real concentration or volumetric signal (see thresholds above). Background scan noise (today's typical 100–300 blocks spread across many IPs with no source ≥ 50) produces *no warning at all* — it never reaches this task. There is no "suppress under N" rule here; if the digest's `warnings` list is empty, exit silently.

### 4. Apply quiet hours

If the warnings list is empty, exit silently (handled by step 2).

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
  - WAN blocks (single source) → `<N> blks from <ip>`
  - WAN blocks (distributed) → `<N> WAN blocks (flood)`
  - State table → `pf state <pct>%`
  - Updates → `updates available`
- Examples:
  - `🚨 1 HIGH · 3 failed UI logins`
  - `⚠️ 2 MEDIUM · cert 12d, 87 blks from 5.6.7.8`
  - `ℹ️ 1 LOW · updates available`
- If multiple warnings, mention the count and the most-severe one.

**Push title**: `OPNsense: <SEVERITY>` (e.g., `OPNsense: HIGH`)

**Persistent (full) message** (multi-line markdown, no length cap):
- Bullet list of all warnings with severity emoji
- Then a "Context" section with the key supporting data:
  - For firewall blocks: top 3 source IPs from `info.firewall.top_blocked_sources_wan` with counts, AND top 3 destination ports from `info.firewall.top_blocked_dest_ports_wan` (port 23/tcp = telnet/Mirai recon, 22/tcp = SSH brute, 3389/tcp = RDP brute, 1900/udp = SSDP amplification — useful at-a-glance shape)
  - For cert warnings: cert descr + exact days
  - For service warnings: list stopped services from `info.services.stopped`
  - For auth (failed): top failed source IPs from `info.auth.top_failed_ips`
  - For auth (successful, only if there's also a failed-login or denied warning to give context on who else is hitting the box): top entries from `info.auth.successful_logins_by_ip` (`<user>@<ip> (<count>x)`)

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

The `tag` makes successive pushes with the same tag *replace* the previous one on the lock screen instead of stacking — so hourly checks don't pile up.

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

## Examples

- Run at 02:00, warnings = [] → no warnings → silent (today's 242 blocks / top source 37 produce no warning — concentration too low)
- Run at 02:00, warnings = ["Pending updates"] → all LOW → defer until 08:00
- Run at 02:00, warnings = ["3 failed UI login attempts", "Pending updates"] → HIGH present → notify
- Run at 02:00, warnings = ["87 WAN blocks from single source 5.6.7.8 (focused scan)"] → MEDIUM → notify (concentration crossed 50)
- Run at 02:00, warnings = ["311 WAN blocks from single source 5.6.7.8 (active scan/brute)"] → HIGH → notify (concentration crossed 200)
- Run at 09:00, warnings = ["Pending updates"] → LOW outside quiet hours → notify
- Run at 09:00, warnings = ["1247 WAN-origin firewall blocks in window (distributed flood)"] → MEDIUM → notify (volumetric, no concentration)