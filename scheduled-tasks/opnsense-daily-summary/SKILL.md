---
name: opnsense-daily-summary
description: Daily 8am OPNsense health summary push notification — heartbeat that monitoring is alive plus 24h roll-up.
---

Send a daily morning summary of the OPNsense firewall's security state. This is a heartbeat — runs every morning at 8am regardless of whether anything is wrong, so the user knows monitoring is still alive.

Each run produces two notifications:
1. A short push to the HA mobile app (one dense line, lock-screen readable)
2. A `persistent_notification` inside HA with the full breakdown (lives in the bell icon)

## Known peers / expected traffic

- **WireGuard peer**: `54.224.141.79` — authorized site-to-site WG endpoint. UDP traffic to/from this IP is expected. Some of it gets incidentally blocked (handshake retries / state churn), which the digest's single-source rule misclassifies as "focused scan" or "active scan/brute". **Treat any "WAN blocks from single source 54.224.141.79 ..." warning as a false positive** — filter it from the warnings list before computing severity. Top-talkers entries for this IP should be shown but labeled `(wg-peer)` per the rule below.

## Steps

### 1. Gather data

Make these calls in parallel (independent — fire in one batch):
- `mcp__opnsense__get_security_digest` with `window_lines=2000` (deeper than the hourly check so daily totals are more representative)
- `mcp__opnsense__get_top_talkers` with `top_n=5` — current bandwidth snapshot (this is rate-now, not 24h totals; useful for catching an actively-running miner / exfil, not for after-the-fact analysis)
- `mcp__opnsense__get_wireguard_status` — site-to-site tunnel health (NPA peer)
- `mcp__opnsense__get_gateway_status` — WAN gateway up/down
- `mcp__opnsense__get_system_status` — memory / swap
- `mcp__opnsense__get_unbound_stats` — DNS resolver health

If any of the four supplemental calls errors, render its body line as `unavailable` and continue (same spirit as the top-talkers fallback) — only a `get_security_digest` failure triggers the failure-mode path.

### 2. Build a status icon and severity

Before classifying, **filter out known false positives**: drop any warning whose text matches `WAN blocks from single source 54.224.141.79` (any variant). This is the WG peer — see "Known peers" above. Note the suppression in the run report so it stays visible.

Determine the highest-severity warning present from the remaining list (same classification as the security-check task):
- HIGH = failed logins / denied actions / stopped services / cert expired / cert <7d / "WAN blocks from single source ... (active scan/brute)" / pf state >=90%
- MEDIUM = cert 7-30d / "WAN blocks from single source ... (focused scan)" / "WAN-origin firewall blocks ... (distributed flood)" / pf state 70-90%
- LOW = pending updates / other unmatched

**Also derive these synthetic warnings** (identical rules to the hourly security-check task) and fold them into the severity decision and the warnings list at the top of the body:
- **WireGuard NPA tunnel DOWN** (HIGH): from `get_wireguard_status`, the `type:"peer"` row named `NPA_Wireguard` has `peer-status` != "online" OR `latest-handshake-age` > 300s. Ignore the `type:"interface"` row (always reads offline).
- **WAN gateway not Online** (HIGH): from `get_gateway_status`, `WAN_DHCP.status_translated` != "Online".
- **Memory/swap pressure** (MEDIUM): from `get_system_status` `Swap:` line, swap used (total − free) > 512M.

The server only emits a WAN-block warning when the shape is meaningful (single source ≥ 50 hits, or total ≥ 1000 with no concentration). Background scan noise produces no warning — so no suppression rule is needed; the digest already filters it out. The persistent body still reports `wan_origin_count` plus top source/port for visibility either way.

If there are no warnings: `✅ All clear`. Otherwise pick the severity emoji (🚨 / ⚠️ / ℹ️).

### 3. Build the short push body (one dense line, target ~100 chars)

Format: `<status> · <key stats inline>`

Stats to include (compact, separated by `·`):
- Logins: `<S>L / <F>fail` (S=successful_count, F=failed_count from info.auth)
- WAN: `<N>blk` (info.firewall.wan_origin_count)
- Stopped svc: only mention if > 0: `<N>svc down`
- Cert next: `cert <N>d` (soonest-expiring in_use cert; "OK" if all > 60d)
- Updates: only mention if available: `updates`
- WireGuard: only mention if down: `WG down`
- WAN gateway: only mention if not Online: `WAN <status>`

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
  - <user>@<ip> (<count>x), <user>@<ip> (<count>x)   ← from info.auth.successful_logins_by_ip, top 3
**WAN blocks**: <wan_origin_count> (LAN-side: <lan_origin_count> — state churn, ignored)
  - Top source: <ip> (<count>x)   ← from info.firewall.top_blocked_sources_wan[0]
  - Top port: <port>/<proto> (<count>x)   ← from info.firewall.top_blocked_dest_ports_wan[0]
**Top talkers (now)**:
  - LAN: <addr> (<rate_bits> bps), <addr> (<rate_bits> bps)   ← top 2 from get_top_talkers
  - WAN: <addr> (<rate_bits> bps), <addr> (<rate_bits> bps)
**Services**: <running> running, <stopped> stopped
**Cert next expiry**: <descr> in <N>d
**Updates**: available (N packages) | none
**pf state table**: <current> / <limit> (<pct>%)
**WireGuard (NPA site-to-site)**: <up — handshake <age>s ago | DOWN (status <peer-status>, last handshake <age>s)>
**WAN gateway**: <status_translated> (<loss> loss / <delay> delay, or "no monitor IP" when ~)
**Memory**: <free> free · swap <used>/<total>
**DNS (Unbound)**: <queries> q · <hit%> cache hit · <avg_ms>ms avg recursion · <timeouts> timeouts (cumulative since resolver start)
**Config changes (window)**: <count> — <classification>
```

**Successful logins detail**: only render the per-user-IP line if `successful_logins_by_ip` is non-empty. Top 3 entries inline. Omit the line if the list is empty.

**Top blocked source/port**: omit each sub-bullet if its list is empty. If `wan_origin_count` is 0, skip the section entirely.

**Top talkers formatting**: convert `rate_bits` to a human-readable rate: `< 1 Mbps` show as `<N> Kbps`, `>= 1 Mbps` show as `<N.N> Mbps`. Skip a row entirely if `rate_bits == 0`. If the addr matches the known WireGuard peer (`54.224.141.79`), append ` (wg-peer)` after the rate so it's clearly tagged as expected traffic rather than something to investigate. If the top-talkers tool returns an error, render `**Top talkers**: unavailable` and continue (don't abort the alert).

**Config changes classification** (use `largest_burst` and `hourly_buckets` from the digest's `info.config_changes`):
- If `count == 0`: render as `**Config changes (window)**: none`
- If `largest_burst.count >= 5`: `<count> — burst (<largest_burst.count> in 1h on <largest_burst.hour>, likely admin session)`
- If `len(hourly_buckets) >= count * 0.7` (i.e. saves spread across many distinct hours): `<count> — steady (likely automation: ACME / dyndns / scheduled tasks)`
- Otherwise: `<count> — mixed`

**WireGuard line**: read the `type:"peer"` row named `NPA_Wireguard` (ignore the `type:"interface"` row — it always reads offline). Healthy = `peer-status: online` with `latest-handshake-age` < ~300s → `up — handshake <age>s ago`. Otherwise → `DOWN ...` and treat as a HIGH warning (step 2). Call errored → `unavailable`.

**WAN gateway line**: from `WAN_DHCP`. Show `status_translated`. `loss`/`delay` read `~` until a monitor IP is configured on the gateway — render `no monitor IP` in that case rather than `~`. Not Online → HIGH warning.

**Memory line**: parse `get_system_status.activity_summary`. Free memory = the `Mem:` line's `<n> Free` field; swap from the `Swap:` line (used = total − free). swap used > 512M → MEDIUM warning.

**DNS (Unbound) line**: from `get_unbound_stats.data.total`: queries = `num.queries`; hit% = `num.cachehits / num.queries * 100` (whole %); avg recursion ms = `recursion.time.avg` × 1000 (1 decimal); timeouts = `num.queries_timed_out`. These counters are cumulative since the resolver last (re)started (`data.time.up` seconds) — a low hit% right after a reboot/upgrade is just a cold cache, NOT a problem. Only treat as noteworthy if `queries_timed_out` is large or `num.queries` is 0 (resolver not serving). Call errored → `unavailable`.

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

If `get_top_talkers` errors but the digest succeeds, render `**Top talkers**: unavailable` in the persistent body and continue normally — don't abort the alert.

Silent failures defeat the purpose of a heartbeat.

## Notes

- Always send this notification, even on a perfectly clean system — that's the heartbeat purpose. Silence would mean "is monitoring even running?"
- The push is for glance value; the persistent is for reading the full state when the user wants details.
- WAN-block stats are always reported in the body (count, top source IP, top dest port) — this is the place to see "internet weather" trends. The server only emits a WAN-block *warning* on concentration or distributed-flood signals, so the body's count is decoupled from whether a warning fires.