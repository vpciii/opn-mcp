# Glossary — Ubiquitous Language

The canonical terms for this project's domain. Use these words exactly
— in code, tests, comments, commits, specs, and conversation. If a
concept needs a name and none exists here, propose one before
inventing an ad-hoc synonym (methodology §3).

One entry per term. Keep definitions short and precise. Note
relationships and any deliberately-excluded near-synonyms.

| Term | Definition | Notes / not to be confused with |
|---|---|---|
| DNAT rule | A Destination NAT (port-forward) rule on the firewall, listed by `get_dnat_rules` and toggled by UUID via `toggle_dnat_rule`. | Not an SNAT rule; the only thing the server can mutate. |
| SNAT rule | A Source NAT (outbound) rule, listed by `get_snat_rules`. | Read-only here. |
| anti-lockout rule | OPNsense's automatic protection of management access, surfacing in the d_nat API as synthetic `lockout_<n>` rows; `toggle_dnat_rule` refuses them structurally (uuid prefix / `is_automatic`), never by description text. | See ADR 0006 (supersedes the string-match mechanism of ADR 0003). Related: the management-path guard, which also refuses rules covering the firewall's own address on the API port. |
| security digest | The aggregated output of `get_security_digest`: auth, blocks, services, updates, certs, pf states, config changes, plus a `warnings` list. | The primary "is anything wrong?" call. |
| warnings | The digest's list of anomaly strings; empty means `status: "ok"`. | Scheduled tasks key on this list, after false-positive filtering. |
| WAN-origin (block) | A pf block whose source IP is public — external scan/brute-force, the real attack signal. | Only WAN-origin blocks feed the digest's scan/flood thresholds. |
| LAN-origin (block) | A pf block whose source IP is private/loopback/link-local/multicast — state-table churn, not an attack. | Split out so it can't trigger false alarms. |
| self-noise | Blocks sourced from the firewall's own IPs or destined to multicast/broadcast (SSDP/mDNS echo) — benign self-chatter. | Code identifier `self_noise`; excluded from WAN attack rankings. |
| filterlog | OPNsense's CSV-format pf firewall log (`filter/latest`), parsed by `_parse_filter_log` (IPv4 only today). | The `firewall` log source alias. |
| pf state table | The firewall's connection-state table; `get_pf_states` reports current/limit/percent with status `ok`/`high`/`critical`. | High utilization signals DDoS or NAT exhaustion. |
| top talkers | Top bandwidth consumers per interface from `get_top_talkers` — rate-now, not 24h totals. | Exfiltration / crypto-miner detection. |
| leases | Active DHCP leases returned by `get_dhcp_leases`. | DHCPv4 (Kea or legacy ISC endpoint). |
| auth events | UI login attempts (successful/failed) plus denied admin actions, parsed from the audit log by `get_auth_events`. | "Failed login" includes unknown-user attempts. |
| denied admin action | An audit-log `action denied` configd entry — a privilege-probe signal. | Distinct from a failed login. |
| config change | A `config-event: new_config` save in the system log, counted by `get_recent_config_changes`; each save creates a `/conf/backup/` snapshot. | Informational — the server can't know which saves were authorized. |
| log source | A `LOG_SOURCES` alias (`firewall`, `audit`, `configd`, …) or raw `module/scope` path passed to `get_log`. | |
| severity tier | The HIGH / MEDIUM / LOW classification a scheduled task assigns each warning, governing whether and when to notify. | Lives in the task prompts, not in `server.py` — see `docs/MONITORING.md`. |
| synthetic warning | A warning a scheduled task derives itself (WireGuard tunnel down, WAN gateway offline, swap pressure) and appends to the digest's `warnings` before classification. | Not emitted by `get_security_digest`. |

## Conventions

- Use the exact casing shown when the term appears as a code
  identifier.
- When two terms are easy to conflate, define both and state the
  distinction explicitly.
- Retire a term by marking it **(deprecated → use `X`)** rather than
  deleting it, so old references remain decodable.
