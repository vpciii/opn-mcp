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

### 0. Note on update freshness (deliberately NO refresh here)

This task does **not** trigger a firmware check. Doing so hits the package mirror and costs ~30–60s on the firewall; running that every hour just to power a LOW-severity, waking-hours-only "updates available" nudge is wasteful. Instead it reads OPNsense's *cached* firmware status, which the **daily 8am summary task refreshes once a day**. So the pending-updates signal here is at most ~24h stale — fine for its purpose. Do not add a `refresh=true` call to this hourly task. (If the cached `last_check` ever looks many days old, that means the daily refresh isn't running — worth investigating, but not by refreshing from here.)

### 1. Gather data (one parallel batch)

Fire these in parallel:
- `mcp__opnsense__get_security_digest` (default window_lines=500) — primary "is anything wrong" call.
- `mcp__opnsense__get_wireguard_status` — site-to-site tunnel health (see step 2b).
- `mcp__opnsense__get_gateway_status` — WAN gateway up/down (see step 2c).
- `mcp__opnsense__get_system_status` — memory/swap pressure (see step 2d).

The digest's `warnings` array is the main signal; steps 2b–2d derive a few extra **synthetic** warnings from the other calls and append them to that list before classification. If any of the three supplemental calls errors, skip just that check (don't abort) and note it in the run report.

### 2. Build the working warnings list, then exit silently if empty

Start from the digest's `warnings` array, apply the false-positive filter (2a), and append any synthetic health warnings (2b–2d). **After all of 2a–2d, if the combined list is empty, exit silently** — no notification, just report "Clean — no warnings (digest + WG + gateway + memory). Exiting silently as expected." and stop. That's the expected case ~99% of the time.

### 2a. Filter known false positives (WireGuard peer)

Drop any digest warning whose text matches `WAN blocks from single source 54.224.141.79` (any variant — focused scan, active scan/brute, etc.). This is the authorized WG peer at `54.224.141.79`; its blocked-UDP noise is not an attack signal. Note this in the run report so the suppression is visible.

### 2b. WireGuard tunnel health (synthetic warning)

From `get_wireguard_status`, find the row with `type: "peer"` and `name: "NPA_Wireguard"` (the site-to-site peer, endpoint `54.224.141.79:51820`). **Ignore the `type: "interface"` row** — it always reports `peer-status: offline` / null handshake and is NOT the tunnel state.

Append a synthetic warning `WireGuard NPA tunnel DOWN (last handshake <age>s ago / status <peer-status>)` if the peer row is missing, OR `peer-status` != `"online"`, OR `latest-handshake-age` (seconds) is `> 300`. A healthy tunnel re-handshakes within its 25s keepalive (age normally < ~180s), so >300s means genuinely down, not a transient miss.

### 2c. WAN gateway health (synthetic warning)

From `get_gateway_status`, check the WAN gateway item (`name: "WAN_DHCP"`). If `status_translated` is not `"Online"` (e.g. "Offline", "Down", "Pending"), append a synthetic warning `WAN gateway <name> is <status_translated>`. Note: `loss`/`delay` are `~` (no monitor IP configured), so only up/down is evaluable today. (If a monitor IP is later set on the gateway, also warn when `loss` > 20% or `delay` is abnormally high.)

### 2d. Memory / swap pressure (synthetic warning)

From `get_system_status.activity_summary`, parse the `Swap:` line (format `Swap: <total> Total, <free> Free`, sizes like `8192M`). Compute swap used = total − free. If swap used is `> 512M`, append a synthetic warning `Memory pressure: swap in use (<used> of <total>)`. Healthy is 0 used; a firewall that has started swapping is an early memory-pressure signal the digest doesn't cover.

### 3. Classify each warning by severity

**HIGH** (notify any time, 24/7):
- Any "failed UI login attempt" warning (any count)
- Any "denied admin action" warning
- Any "service(s) not running" warning
- Any "Certificate ... is EXPIRED and in use" warning
- Any "Certificate ... expires in N d" where N < 7
- Any "WAN blocks from single source ... (active scan/brute)" warning (server emits this when one source ≥ 200 hits)
- Any "pf state table" warning where percent >= 90 (critical)
- `WireGuard NPA tunnel DOWN ...` (synthetic — site-to-site link lost)
- `WAN gateway ... is <not Online>` (synthetic — WAN/gateway down)

**MEDIUM** (notify any time, 24/7):
- "Certificate ... expires in N d" where 7 <= N < 30
- "WAN blocks from single source ... (focused scan)" warning (server emits this when one source ≥ 50 hits)
- "WAN-origin firewall blocks ... (distributed flood)" warning (server emits this when total ≥ 1000 with no single dominant source)
- "pf state table" where 70 <= percent < 90
- `Memory pressure: swap in use ...` (synthetic — early memory-pressure signal)

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
  - WireGuard tunnel down → `WG NPA tunnel down`
  - WAN gateway down → `WAN gw <status>`
  - Memory/swap pressure → `swap in use <used>`
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
  - For the WireGuard warning: peer name, `peer-status`, last-handshake age (seconds), and endpoint from the `type:"peer"` row
  - For the gateway warning: gateway name and `status_translated` (plus `loss`/`delay` once a monitor IP is configured)
  - For the memory warning: swap used / total, plus free memory from the `Mem:` line

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
- Keep the tool set tight: the digest plus the three health calls (`get_wireguard_status`, `get_gateway_status`, `get_system_status`) are all that should run. Don't add further tools or deep log-diving — this must stay fast and predictable.

## Examples

- Run at 02:00, warnings = [] → no warnings → silent (today's 242 blocks / top source 37 produce no warning — concentration too low)
- Run at 02:00, warnings = ["Pending updates"] → all LOW → defer until 08:00
- Run at 02:00, warnings = ["3 failed UI login attempts", "Pending updates"] → HIGH present → notify
- Run at 02:00, warnings = ["87 WAN blocks from single source 5.6.7.8 (focused scan)"] → MEDIUM → notify (concentration crossed 50)
- Run at 02:00, warnings = ["311 WAN blocks from single source 5.6.7.8 (active scan/brute)"] → HIGH → notify (concentration crossed 200)
- Run at 09:00, warnings = ["Pending updates"] → LOW outside quiet hours → notify
- Run at 09:00, warnings = ["1247 WAN-origin firewall blocks in window (distributed flood)"] → MEDIUM → notify (volumetric, no concentration)