"""MCP server for read-only OPNsense firewall monitoring."""

import collections
import ipaddress
import os
import re
import ssl
import time
from datetime import datetime
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

# --- Configuration ---

OPNSENSE_HOST = os.environ.get("OPNSENSE_HOST", "192.168.1.1")
OPNSENSE_API_KEY = os.environ.get("OPNSENSE_API_KEY", "")
OPNSENSE_API_SECRET = os.environ.get("OPNSENSE_API_SECRET", "")
OPNSENSE_VERIFY_SSL = os.environ.get("OPNSENSE_VERIFY_SSL", "false").lower() == "true"

BASE_URL = f"https://{OPNSENSE_HOST}/api"

mcp = FastMCP("opn-mcp")


def _client() -> httpx.AsyncClient:
    """Create an httpx client configured for the OPNsense API."""
    verify: bool | ssl.SSLContext = OPNSENSE_VERIFY_SSL
    if not OPNSENSE_VERIFY_SSL:
        # Create an SSL context that doesn't verify certificates
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        verify = ctx

    return httpx.AsyncClient(
        base_url=BASE_URL,
        auth=(OPNSENSE_API_KEY, OPNSENSE_API_SECRET),
        verify=verify,
        timeout=30.0,
        # Ignore HTTP(S)_PROXY / NO_PROXY env vars. The OPNsense API is on the
        # LAN and shouldn't be routed through a proxy. This also avoids httpx
        # choking on unbracketed IPv6 CIDRs in NO_PROXY (e.g. those injected
        # by OrbStack), which raise "Invalid port" during client construction.
        trust_env=False,
    )


async def _get(path: str) -> dict | list | str:
    """Make a GET request to the OPNsense API."""
    async with _client() as client:
        resp = await client.get(path)
        resp.raise_for_status()
        return resp.json()


async def _post(path: str, json: dict | None = None) -> dict | list | str:
    """Make a POST request to the OPNsense API (used for some read-only diagnostics)."""
    async with _client() as client:
        resp = await client.post(path, json=json or {})
        resp.raise_for_status()
        return resp.json()


def _error(msg: str) -> dict:
    return {"error": msg}


def _fmt_exc(e: BaseException) -> str:
    """Format an exception with its type so empty-message errors are still useful."""
    msg = str(e).strip()
    type_name = type(e).__name__
    return f"{type_name}: {msg}" if msg else type_name


# --- Tools ---


@mcp.tool()
async def get_system_status() -> dict:
    """Get OPNsense system status: firmware version, uptime, CPU/memory/disk usage, and temperature if available."""
    try:
        # Gather system info from multiple endpoints
        results = {}

        async with _client() as client:
            # Firmware / version info
            try:
                r = await client.get("/core/firmware/status")
                r.raise_for_status()
                fw = r.json()
                results["firmware"] = {
                    "product_name": fw.get("product_name"),
                    "product_version": fw.get("product_version"),
                    "os_version": fw.get("os_version"),
                }
            except Exception as e:
                results["firmware"] = _error(_fmt_exc(e))

            # System resources via activity endpoint
            try:
                r = await client.get("/diagnostics/activity/getActivity")
                r.raise_for_status()
                activity = r.json()
                headers = activity.get("headers", "")
                results["activity_summary"] = headers
            except Exception as e:
                results["activity"] = _error(_fmt_exc(e))

            # System info (uptime, etc.)
            try:
                r = await client.get("/diagnostics/system/system_information")
                r.raise_for_status()
                results["system_info"] = r.json()
            except Exception as e:
                results["system_info"] = _error(_fmt_exc(e))

            # Temperature (HAProxy health or system temps)
            try:
                r = await client.get("/diagnostics/system/system_temperature")
                r.raise_for_status()
                results["temperature"] = r.json()
            except Exception:
                results["temperature"] = "not available"

        return results
    except Exception as e:
        return _error(f"Failed to get system status: {_fmt_exc(e)}")


@mcp.tool()
async def get_interfaces() -> dict:
    """Get all network interfaces with name, status, IP address, MAC address, and traffic counters."""
    try:
        data = await _get("/diagnostics/interface/getInterfaceStatistics")
        return data
    except Exception as e:
        return _error(f"Failed to get interfaces: {_fmt_exc(e)}")


@mcp.tool()
async def get_gateway_status() -> dict:
    """Get all gateways with name, IP, status, RTT, and packet loss."""
    try:
        data = await _post("/routes/gateway/status")
        return data
    except Exception as e:
        return _error(f"Failed to get gateway status: {_fmt_exc(e)}")


@mcp.tool()
async def get_dhcp_leases() -> dict:
    """Get all active DHCP leases with hostname, IP, MAC address, and expiry time."""
    try:
        # Try DHCPv4 leases via the Kea or ISC endpoint
        try:
            data = await _get("/dhcpv4/leases/searchLease")
            return data
        except Exception:
            pass

        # Fallback: try the legacy leases endpoint
        data = await _get("/dhcpv4/service/searchLease")
        return data
    except Exception as e:
        return _error(f"Failed to get DHCP leases: {_fmt_exc(e)}")


LOG_SOURCES = {
    # The pf/filter path returns nothing on modern OPNsense; the real filterlog
    # output lives at /var/log/filter/latest.log.
    "firewall": "filter/latest",
    "audit": "core/audit",
    "configd": "core/configd",
    "kernel": "core/kernel",
    "system": "core/system",
    "resolver": "core/resolver",
    "routing": "core/routing",
    "wireless": "core/wireless",
    "lighttpd": "core/lighttpd",
    "pkg": "core/pkg",
    "ipsec": "ipsec/ipsec",
    "openvpn": "openvpn/openvpn",
    "wireguard": "wireguard/wireguard",
    "ntpd": "ntpd/ntpd",
    "monit": "monit/monit",
    "captiveportal": "captiveportal/portalauth",
    "dnsmasq": "dnsmasq/dnsmasq",
    "dhcpd": "dhcpd/dhcpd",
}


async def _fetch_log(
    source: str,
    limit: int = 50,
    severity: str = "",
    search: str = "",
) -> dict:
    """Internal log fetch. Raises on error; used by get_log and the security tools."""
    path = LOG_SOURCES.get(source, source)
    if path.count("/") != 1:
        raise ValueError(
            f"Unknown log source '{source}'. Pass a known alias or 'module/scope'."
        )
    body: dict = {"rowCount": limit, "current": 1}
    if severity:
        body["severity"] = severity
    if search:
        body["searchPhrase"] = search
    async with _client() as client:
        resp = await client.post(f"/diagnostics/log/{path}", json=body)
        resp.raise_for_status()
        return resp.json()


@mcp.tool()
async def get_log(
    source: str = "firewall",
    limit: int = 50,
    severity: str = "",
    search: str = "",
) -> dict:
    """Get recent OPNsense log entries.

    Source aliases: 'firewall' (pf filterlog), 'audit', 'configd', 'kernel',
    'system', 'resolver', 'routing', 'wireless', 'lighttpd', 'pkg', 'ipsec',
    'openvpn', 'wireguard', 'ntpd', 'monit', 'captiveportal', 'dnsmasq',
    'dhcpd'. Alternatively pass a raw 'module/scope' path (e.g. 'filter/latest').

    Optional: severity (e.g. 'Error', 'Warning', 'Notice', 'Informational'),
    search (free-text phrase).
    """
    try:
        return await _fetch_log(source, limit=limit, severity=severity, search=search)
    except Exception as e:
        return _error(f"Failed to get '{source}' log: {_fmt_exc(e)}")


@mcp.tool()
async def get_wireguard_status() -> dict:
    """Get WireGuard VPN instances and peer connection status."""
    try:
        data = await _get("/wireguard/service/show")
        return data
    except Exception as e:
        return _error(f"Failed to get WireGuard status: {_fmt_exc(e)}")


@mcp.tool()
async def get_arp_table() -> dict:
    """Get the current ARP table with IP, MAC address, interface, and hostname."""
    try:
        data = await _get("/diagnostics/interface/getArp")
        return data
    except Exception as e:
        return _error(f"Failed to get ARP table: {_fmt_exc(e)}")


@mcp.tool()
async def get_unbound_stats() -> dict:
    """Get Unbound DNS resolver statistics including cache hits, misses, and query counts."""
    try:
        # Current API path (OPNsense >= 23.1). The legacy /unbound/service/dnsStats
        # was removed; stats now live under the diagnostics controller.
        data = await _get("/unbound/diagnostics/stats")
        return data
    except Exception as e:
        return _error(f"Failed to get Unbound stats: {_fmt_exc(e)}")


@mcp.tool()
async def ping_host(target: str, count: int = 3) -> dict:
    """Run a ping from OPNsense to a target host. This is a read-only diagnostic tool."""
    try:
        async with _client() as client:
            resp = await client.post(
                "/diagnostics/interface/ping",
                json={"address": target, "count": str(count)},
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        return _error(f"Failed to ping {target}: {_fmt_exc(e)}")


@mcp.tool()
async def get_openvpn_status() -> dict:
    """Get OpenVPN server and client status including connected peers, if configured."""
    try:
        results = {}

        async with _client() as client:
            # OpenVPN server sessions
            try:
                r = await client.get("/openvpn/service/searchSessions")
                r.raise_for_status()
                results["sessions"] = r.json()
            except Exception as e:
                results["sessions"] = _error(_fmt_exc(e))

            # OpenVPN instances
            try:
                r = await client.get("/openvpn/instances/search")
                r.raise_for_status()
                results["instances"] = r.json()
            except Exception as e:
                results["instances"] = _error(_fmt_exc(e))

        return results
    except Exception as e:
        return _error(f"Failed to get OpenVPN status: {_fmt_exc(e)}")


@mcp.tool()
async def get_tailscale_status() -> dict:
    """Get Tailscale plugin service status and configured settings. Requires the os-tailscale plugin."""
    try:
        results = {}

        async with _client() as client:
            try:
                r = await client.get("/tailscale/service/status")
                r.raise_for_status()
                results["service"] = r.json()
            except Exception as e:
                results["service"] = _error(_fmt_exc(e))

            try:
                r = await client.get("/tailscale/settings/get")
                r.raise_for_status()
                results["settings"] = r.json()
            except Exception as e:
                results["settings"] = _error(_fmt_exc(e))

        return results
    except Exception as e:
        return _error(f"Failed to get Tailscale status: {_fmt_exc(e)}")


@mcp.tool()
async def get_firewall_rules() -> dict:
    """Get all firewall filter rules with source, destination, port, protocol, action, and status."""
    try:
        data = await _get("/firewall/filter/searchRule")
        return data
    except Exception as e:
        return _error(f"Failed to get firewall rules: {_fmt_exc(e)}")


@mcp.tool()
async def get_dnat_rules() -> dict:
    """Get all Destination NAT (port-forward) rules with source, destination, ports, and target."""
    try:
        data = await _get("/firewall/d_nat/searchRule")
        return data
    except Exception as e:
        return _error(f"Failed to get DNAT rules: {_fmt_exc(e)}")


@mcp.tool()
async def get_snat_rules() -> dict:
    """Get all Source NAT (outbound) rules."""
    try:
        data = await _get("/firewall/source_nat/searchRule")
        return data
    except Exception as e:
        return _error(f"Failed to get SNAT rules: {_fmt_exc(e)}")


@mcp.tool()
async def toggle_dnat_rule(uuid: str, enabled: bool) -> dict:
    """Enable or disable a Destination NAT rule by UUID. Anti-lockout rules cannot be modified."""
    try:
        async with _client() as client:
            # Fetch the rule first to check for anti-lockout
            r = await client.get(f"/firewall/d_nat/getRule/{uuid}")
            r.raise_for_status()
            rule = r.json()

            # Check for anti-lockout rules
            rule_data = rule.get("rule", rule)
            description = str(rule_data.get("description", "")).lower()
            if "anti-lockout" in description or "antilockout" in description:
                return _error("Refusing to modify anti-lockout rule.")

            # Toggle: disabled=0 means enabled, disabled=1 means disabled
            disabled = "0" if enabled else "1"
            r = await client.post(f"/firewall/d_nat/toggleRule/{uuid}/{disabled}")
            r.raise_for_status()
            toggle_result = r.json()

            # Apply the changes so they take effect
            r = await client.post("/firewall/d_nat/apply")
            r.raise_for_status()
            apply_result = r.json()

            return {
                "toggle": toggle_result,
                "apply": apply_result,
                "status": "enabled" if enabled else "disabled",
            }
    except Exception as e:
        return _error(f"Failed to toggle DNAT rule: {_fmt_exc(e)}")


# --- Security monitoring tools ---


# Pattern matching audit-log lines like:
#   /index.php: Successful login for user 'vince.ciganik' from: 10.216.1.18
#   /index.php: Failed login for user 'X' from: 1.2.3.4
#   /index.php: Failed login attempt for unknown user 'X' from: 1.2.3.4
_LOGIN_RE = re.compile(
    r"(?P<result>Successful|Failed)\s+login(?:\s+attempt)?"
    r"\s+for\s+(?:unknown\s+)?user\s+'(?P<user>[^']*)'"
    r"\s+from:\s*(?P<ip>\S+)"
)


def _is_lan_origin(ip: str | None) -> bool:
    """True if the source IP is in private/loopback/link-local space.

    Used to split firewall blocks by where they came from:
      - LAN-origin (private src) → almost always state-table churn or local
        device misconfig; not an attack.
      - WAN-origin (public src)  → external scans, brute-force probes, real
        attack signal.

    The digest's "possible scan/flood" warning thresholds only on WAN-origin
    blocks so a routine state-table flush after a config reload doesn't
    trigger a false alarm from chatty LAN devices retransmitting orphaned
    FIN/PSH packets.
    """
    if not ip:
        return False
    try:
        addr = ipaddress.ip_address(ip)
    except (ValueError, TypeError):
        return False
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def _parse_filter_log(rows: list[dict]) -> list[dict]:
    """Parse OPNsense filterlog CSV lines into structured dicts.

    The OPNsense filter log uses comma-separated fields; layout depends on IP
    version and protocol. We handle the common case (IPv4 + TCP/UDP/ICMP) and
    skip entries we can't parse cleanly.

    Reference layout (IPv4):
      0=rule_num, 1=sub_rule, 2=anchor, 3=tracker, 4=interface, 5=reason,
      6=action, 7=direction, 8=ip_ver, 9=tos, 10=ecn, 11=ttl, 12=id, 13=offset,
      14=flags, 15=proto_id, 16=proto_text, 17=length, 18=src_ip, 19=dst_ip,
      20=src_port (tcp/udp), 21=dst_port (tcp/udp)
    """
    parsed = []
    for row in rows:
        line = (row.get("line") or "").strip()
        if not line:
            continue
        parts = line.split(",")
        if len(parts) < 18:
            continue
        try:
            ip_ver = parts[8]
            if ip_ver != "4":
                # IPv6 layout differs; skipping for now (rare on home WANs)
                continue
            proto = parts[16] if len(parts) > 16 else ""
            entry = {
                "timestamp": row.get("timestamp"),
                "interface": parts[4] or None,
                "action": parts[6] or None,
                "direction": parts[7] or None,
                "proto": proto or None,
                "src_ip": parts[18] if len(parts) > 18 else None,
                "dst_ip": parts[19] if len(parts) > 19 else None,
                "src_port": (
                    parts[20] if len(parts) > 20 and proto in ("tcp", "udp") else None
                ),
                "dst_port": (
                    parts[21] if len(parts) > 21 and proto in ("tcp", "udp") else None
                ),
                "rule_id": parts[0] or None,
            }
            parsed.append(entry)
        except (IndexError, ValueError):
            continue
    return parsed


@mcp.tool()
async def get_services() -> dict:
    """List all OPNsense services with their running state.

    Highlights any service that is currently stopped — useful for catching
    crashed daemons (Unbound, dhcpd, configd, etc.) without trawling logs.
    """
    try:
        data = await _get("/core/service/search")
        rows = data.get("rows", []) if isinstance(data, dict) else []
        running = [r for r in rows if r.get("running")]
        stopped = [r for r in rows if not r.get("running")]
        return {
            "total": len(rows),
            "running_count": len(running),
            "stopped_count": len(stopped),
            "stopped_services": [
                {
                    "name": s.get("name"),
                    "description": s.get("description"),
                    "id": s.get("id"),
                }
                for s in stopped
            ],
            "all_services": rows,
        }
    except Exception as e:
        return _error(f"Failed to get services: {_fmt_exc(e)}")


@mcp.tool()
async def get_updates_available(refresh: bool = False) -> dict:
    """Check for pending OPNsense and package updates.

    Reads the cached firmware status (last refresh timestamp included). If
    refresh=True, triggers a fresh check on the firewall first; the check is
    asynchronous on the OPNsense side, so the returned status may still
    reflect a previous run if the new check hasn't completed.
    """
    try:
        if refresh:
            try:
                await _post("/core/firmware/check")
                # Brief grace period; the actual check runs in background.
                import asyncio

                await asyncio.sleep(3)
            except Exception:
                pass

        status: Any = await _get("/core/firmware/status")
        if not isinstance(status, dict):
            return _error("Unexpected firmware status response shape")

        upgrade_packages = status.get("upgrade_packages", []) or []
        new_packages = status.get("new_packages", []) or []
        reinstall_packages = status.get("reinstall_packages", []) or []
        remove_packages = status.get("remove_packages", []) or []

        return {
            "updates_available": status.get("status") == "ok",
            "status_msg": status.get("status_msg"),
            "last_check": status.get("last_check"),
            "current_version": status.get("product_version"),
            "needs_reboot": status.get("upgrade_needs_reboot") in ("1", 1, True),
            "download_size": status.get("download_size"),
            "package_counts": {
                "upgrade": len(upgrade_packages),
                "new": len(new_packages),
                "reinstall": len(reinstall_packages),
                "remove": len(remove_packages),
            },
            "upgrade_packages": upgrade_packages,
            "new_packages": new_packages,
            "reinstall_packages": reinstall_packages,
            "remove_packages": remove_packages,
            "upgrade_major_version": status.get("upgrade_major_version") or "",
            "upgrade_major_message": status.get("upgrade_major_message") or "",
        }
    except Exception as e:
        return _error(f"Failed to get update status: {_fmt_exc(e)}")


async def _scan_audit_logins(limit: int) -> tuple[list[dict], list[dict]]:
    """Fetch recent UI login attempts from the audit log.

    Uses server-side search filter so chatty configd entries (which dominate
    the audit log on busy systems) don't push login records out of the window.
    Returns (successful, failed) lists.
    """
    raw = await _fetch_log("audit", limit=limit, search="login")
    rows = raw.get("rows", []) if isinstance(raw, dict) else []
    successful: list[dict] = []
    failed: list[dict] = []
    for row in rows:
        line = row.get("line") or ""
        m = _LOGIN_RE.search(line)
        if not m:
            continue
        entry = {
            "timestamp": row.get("timestamp"),
            "user": m.group("user"),
            "source_ip": m.group("ip"),
        }
        (successful if m.group("result") == "Successful" else failed).append(entry)
    return successful, failed


async def _scan_audit_denied(limit: int) -> list[dict]:
    """Fetch denied configd admin actions (privilege-probe signal)."""
    raw = await _fetch_log("audit", limit=limit, search="denied")
    rows = raw.get("rows", []) if isinstance(raw, dict) else []
    denied: list[dict] = []
    for row in rows:
        line = (row.get("line") or "").strip()
        if not line.startswith("action denied"):
            continue
        parts = line.split()
        action_name = parts[2] if len(parts) > 2 else None
        user = parts[-1] if len(parts) >= 6 and parts[-2] == "user" else None
        denied.append(
            {
                "timestamp": row.get("timestamp"),
                "action": action_name,
                "user": user,
                "line": line,
            }
        )
    return denied


@mcp.tool()
async def get_auth_events(limit: int = 200) -> dict:
    """Recent UI login attempts (success and failure) plus denied admin actions.

    Pulls from the audit log via two server-filtered queries (one for "login",
    one for "denied") so chatty configd action-allowed entries don't crowd out
    the records we actually care about.

    Returns counts, recent exemplars, and top source IPs of failed logins.
    """
    try:
        successful, failed = await _scan_audit_logins(limit)
        denied_actions = await _scan_audit_denied(limit)

        failed_by_ip = collections.Counter(
            e["source_ip"] for e in failed if e.get("source_ip")
        )
        successful_users = sorted({e["user"] for e in successful if e.get("user")})

        return {
            "successful_count": len(successful),
            "failed_count": len(failed),
            "denied_action_count": len(denied_actions),
            "successful_users": successful_users,
            "top_failed_source_ips": [
                {"ip": ip, "count": c} for ip, c in failed_by_ip.most_common(10)
            ],
            "recent_failed": failed[:20],
            "recent_denied_actions": denied_actions[:20],
            "recent_successful": successful[:10],
            "window_size": limit,
        }
    except Exception as e:
        return _error(f"Failed to get auth events: {_fmt_exc(e)}")


@mcp.tool()
async def get_firewall_blocks(limit: int = 500, top_n: int = 10) -> dict:
    """Aggregate recent pf block events: top source IPs, top destination ports.

    Pulls the most recent `limit` filterlog entries, parses CSV, isolates
    action=block, and splits results by source-IP origin:

      - **WAN-origin** (public source IP) — external scans, brute-force probes,
        real attack signal
      - **LAN-origin** (private source IP) — almost always pf state-table churn
        from idle/restart-orphaned TCP sessions trying to close gracefully;
        cosmetic noise, not an attack

    Top-N rankings are computed for the WAN-origin set so legitimate attack
    sources don't get crowded out by chatty LAN devices.
    """
    try:
        raw = await _fetch_log("firewall", limit=limit)
        rows = raw.get("rows", []) if isinstance(raw, dict) else []
        parsed = _parse_filter_log(rows)
        blocks = [e for e in parsed if e.get("action") == "block"]
        passes = [e for e in parsed if e.get("action") == "pass"]

        wan_blocks = [e for e in blocks if not _is_lan_origin(e.get("src_ip"))]
        lan_blocks = [e for e in blocks if _is_lan_origin(e.get("src_ip"))]

        by_src = collections.Counter(
            e["src_ip"] for e in wan_blocks if e.get("src_ip")
        )
        by_dst_port = collections.Counter(
            f"{e['dst_port']}/{e['proto']}"
            for e in wan_blocks
            if e.get("dst_port") and e.get("proto")
        )
        by_interface = collections.Counter(
            e["interface"] for e in blocks if e.get("interface")
        )
        lan_top_src = collections.Counter(
            e["src_ip"] for e in lan_blocks if e.get("src_ip")
        )

        return {
            "window_lines": len(rows),
            "parsed_v4_count": len(parsed),
            "block_count": len(blocks),
            "wan_origin_count": len(wan_blocks),
            "lan_origin_count": len(lan_blocks),
            "pass_count": len(passes),
            "top_source_ips": [
                {"ip": ip, "count": c} for ip, c in by_src.most_common(top_n)
            ],
            "top_dest_ports": [
                {"port": p, "count": c} for p, c in by_dst_port.most_common(top_n)
            ],
            "by_interface": [
                {"interface": i, "count": c} for i, c in by_interface.most_common()
            ],
            "lan_origin_top_sources": [
                {"ip": ip, "count": c} for ip, c in lan_top_src.most_common(top_n)
            ],
            "recent_blocks": blocks[:20],
        }
    except Exception as e:
        return _error(f"Failed to get firewall blocks: {_fmt_exc(e)}")


@mcp.tool()
async def get_security_digest(window_lines: int = 500) -> dict:
    """Compact security overview — the primary 'is anything wrong?' call.

    Aggregates auth attempts, denied admin actions, firewall blocks, service
    health, and pending updates into one response. Returns counts plus a few
    exemplars (no raw log dumps), and a 'warnings' list highlighting anything
    that looks anomalous so callers can fast-path on len(warnings) > 0.

    `window_lines` controls how deep into the audit / filter log we sweep
    (default 500). Larger windows catch slower-burning patterns at the cost
    of more API work.
    """
    digest: dict[str, Any] = {"warnings": [], "info": {}}

    # --- Auth events ---
    try:
        successful, failed = await _scan_audit_logins(window_lines)
        denied = await _scan_audit_denied(window_lines)
        failed_by_ip = collections.Counter(
            e["source_ip"] for e in failed if e.get("source_ip")
        )
        successful_by_user_ip = collections.Counter(
            (e["user"], e["source_ip"])
            for e in successful
            if e.get("user") and e.get("source_ip")
        )
        digest["info"]["auth"] = {
            "successful_count": len(successful),
            "failed_count": len(failed),
            "successful_users": sorted({e["user"] for e in successful if e.get("user")}),
            "successful_logins_by_ip": [
                {"user": u, "ip": ip, "count": c}
                for (u, ip), c in successful_by_user_ip.most_common(10)
            ],
            "denied_admin_actions": len(denied),
            "top_failed_ips": [
                {"ip": ip, "count": c} for ip, c in failed_by_ip.most_common(5)
            ],
        }
        if failed:
            digest["warnings"].append(
                f"{len(failed)} failed UI login attempt(s) in window"
            )
        if denied:
            digest["warnings"].append(
                f"{len(denied)} denied admin action(s) in window (possible privilege probe)"
            )
    except Exception as e:
        digest["info"]["auth"] = {"error": _fmt_exc(e)}

    # --- Firewall blocks ---
    try:
        raw = await _fetch_log("firewall", limit=window_lines)
        rows = raw.get("rows", []) if isinstance(raw, dict) else []
        parsed = _parse_filter_log(rows)
        blocks = [e for e in parsed if e.get("action") == "block"]
        wan_blocks = [e for e in blocks if not _is_lan_origin(e.get("src_ip"))]
        lan_blocks = [e for e in blocks if _is_lan_origin(e.get("src_ip"))]
        wan_by_src = collections.Counter(
            e["src_ip"] for e in wan_blocks if e.get("src_ip")
        )
        wan_by_dst_port = collections.Counter(
            f"{e['dst_port']}/{e['proto']}"
            for e in wan_blocks
            if e.get("dst_port") and e.get("proto")
        )
        digest["info"]["firewall"] = {
            "block_count": len(blocks),
            "wan_origin_count": len(wan_blocks),
            "lan_origin_count": len(lan_blocks),
            "pass_count": sum(1 for e in parsed if e.get("action") == "pass"),
            "top_blocked_sources_wan": [
                {"ip": ip, "count": c} for ip, c in wan_by_src.most_common(5)
            ],
            "top_blocked_dest_ports_wan": [
                {"port": p, "count": c} for p, c in wan_by_dst_port.most_common(5)
            ],
        }
        # WAN-block alerting: prefer *concentration* over raw volume. Total
        # volume scales with baseline internet scanner noise, but a single
        # source dominating means focused activity (SSH brute / vuln scan /
        # worm pivot) which is the actionable signal. Three gates, ordered
        # most-specific first:
        #   1. Single source >= 200 hits → HIGH (active brute/scan)
        #   2. Single source >= 50 hits  → MEDIUM (focused scan)
        #   3. Total >= 1000 distributed → MEDIUM (distributed flood / DDoS)
        # LAN-origin blocks are excluded — they're nearly always pf
        # state-table churn after config reload or session timeout.
        top = wan_by_src.most_common(1)
        top_src_ip, top_src_count = top[0] if top else (None, 0)
        if top_src_count >= 200:
            digest["warnings"].append(
                f"{top_src_count} WAN blocks from single source {top_src_ip} "
                "(active scan/brute)"
            )
        elif top_src_count >= 50:
            digest["warnings"].append(
                f"{top_src_count} WAN blocks from single source {top_src_ip} "
                "(focused scan)"
            )
        elif len(wan_blocks) >= 1000:
            digest["warnings"].append(
                f"{len(wan_blocks)} WAN-origin firewall blocks in window "
                "(distributed flood)"
            )
    except Exception as e:
        digest["info"]["firewall"] = {"error": _fmt_exc(e)}

    # --- Service health ---
    try:
        svc = await _get("/core/service/search")
        rows = svc.get("rows", []) if isinstance(svc, dict) else []
        stopped = [
            {"name": s.get("name"), "description": s.get("description")}
            for s in rows
            if not s.get("running")
        ]
        digest["info"]["services"] = {
            "total": len(rows),
            "stopped_count": len(stopped),
            "stopped": stopped,
        }
        if stopped:
            digest["warnings"].append(
                f"{len(stopped)} service(s) not running: "
                + ", ".join(s["name"] or "?" for s in stopped[:5])
            )
    except Exception as e:
        digest["info"]["services"] = {"error": _fmt_exc(e)}

    # --- Updates ---
    try:
        status: Any = await _get("/core/firmware/status")
        if isinstance(status, dict):
            # Trust the package count, not the status string. OPNsense returns
            # status="ok" when there's nothing to update and other strings
            # (e.g. "update", "upgrade") when there are; the previous check
            # had this inverted and silently masked pending updates.
            package_count = len(status.get("upgrade_packages", []) or []) + len(
                status.get("new_packages", []) or []
            )
            available = package_count > 0
            digest["info"]["updates"] = {
                "available": available,
                "status_msg": status.get("status_msg"),
                "current_version": status.get("product_version"),
                "last_check": status.get("last_check"),
                "package_count": package_count,
            }
            if available:
                digest["warnings"].append(
                    f"Pending OPNsense / package updates ({package_count} packages)"
                )
        else:
            digest["info"]["updates"] = {"error": "unexpected response"}
    except Exception as e:
        digest["info"]["updates"] = {"error": _fmt_exc(e)}

    # --- Certificates ---
    try:
        cert_summary = await _check_certs()
        digest["info"]["certificates"] = cert_summary
        for c in cert_summary.get("expiring_soon", []):
            digest["warnings"].append(
                f"Certificate '{c['descr']}' expires in {c['days_until_expiry']}d"
            )
        for c in cert_summary.get("expired_in_use", []):
            digest["warnings"].append(
                f"Certificate '{c['descr']}' is EXPIRED and in use"
            )
    except Exception as e:
        digest["info"]["certificates"] = {"error": _fmt_exc(e)}

    # --- PF state table ---
    try:
        st = await _get("/diagnostics/firewall/pf_states")
        if isinstance(st, dict):
            current = int(st.get("current", 0) or 0)
            limit = int(st.get("limit", 0) or 0)
            pct = round(current / limit * 100, 2) if limit else None
            digest["info"]["pf_states"] = {
                "current": current,
                "limit": limit,
                "percent_used": pct,
            }
            if pct is not None and pct >= 80:
                digest["warnings"].append(
                    f"pf state table {pct}% full ({current}/{limit}) — "
                    "possible DDoS or NAT exhaustion"
                )
    except Exception as e:
        digest["info"]["pf_states"] = {"error": _fmt_exc(e)}

    # --- Recent config changes (informational) ---
    try:
        changes = await _count_config_changes(window_lines)
        digest["info"]["config_changes"] = changes
        # Informational only — we can't know what's authorized. Surface count
        # so the user can compare against their own activity.
    except Exception as e:
        digest["info"]["config_changes"] = {"error": _fmt_exc(e)}

    digest["status"] = "ok" if not digest["warnings"] else "warnings"
    return digest


# --- Pass 2: cert, state-table, talker, routing tools ---


async def _check_certs(near_expiry_days: int = 30) -> dict:
    """Fetch all certs, classify by status. Returns counts + flagged subsets.

    Status categories (per cert):
      - ok        : in_use or not, valid for >= near_expiry_days
      - warning   : in_use AND days_until_expiry < near_expiry_days
      - expired   : valid_to < now (expired)
      - inactive  : in_use=0 (regardless of expiry — informational)

    The digest only warns on in-use+near-expiry or in-use+expired.
    """
    raw = await _get("/trust/cert/search")
    rows = raw.get("rows", []) if isinstance(raw, dict) else []
    now = time.time()
    summary: list[dict] = []
    expiring_soon: list[dict] = []
    expired_in_use: list[dict] = []
    for r in rows:
        try:
            valid_to = int(r.get("valid_to", 0) or 0)
        except (ValueError, TypeError):
            valid_to = 0
        try:
            valid_from = int(r.get("valid_from", 0) or 0)
        except (ValueError, TypeError):
            valid_from = 0
        in_use = str(r.get("in_use", "0")) == "1"
        days_left = int((valid_to - now) // 86400) if valid_to else None

        entry = {
            "uuid": r.get("uuid"),
            "descr": r.get("descr") or r.get("commonname"),
            "commonname": r.get("commonname"),
            "in_use": in_use,
            "valid_from_epoch": valid_from or None,
            "valid_to_epoch": valid_to or None,
            "days_until_expiry": days_left,
            "expired": days_left is not None and days_left < 0,
        }
        summary.append(entry)
        if in_use:
            if entry["expired"]:
                expired_in_use.append(entry)
            elif days_left is not None and 0 <= days_left < near_expiry_days:
                expiring_soon.append(entry)

    return {
        "total": len(summary),
        "in_use_count": sum(1 for c in summary if c["in_use"]),
        "expired_in_use": expired_in_use,
        "expiring_soon": expiring_soon,
        "near_expiry_threshold_days": near_expiry_days,
        "all_certs": summary,
    }


async def _count_config_changes(window_lines: int) -> dict:
    """Count config-event entries in the recent system log."""
    raw = await _fetch_log("system", limit=window_lines, search="config-event: new_config")
    rows = raw.get("rows", []) if isinstance(raw, dict) else []
    timestamps = [r.get("timestamp") for r in rows if r.get("timestamp")]

    buckets: collections.Counter[str] = collections.Counter()
    for ts in timestamps:
        try:
            bucket = datetime.fromisoformat(ts).replace(minute=0, second=0, microsecond=0)
            buckets[bucket.isoformat()] += 1
        except (ValueError, TypeError):
            continue

    hourly_buckets = [
        {"hour": hour, "count": count}
        for hour, count in sorted(buckets.items(), reverse=True)
    ]
    largest_burst = (
        max(hourly_buckets, key=lambda b: b["count"]) if hourly_buckets else None
    )

    return {
        "count": len(rows),
        "latest_timestamps": timestamps[:10],
        "hourly_buckets": hourly_buckets,
        "largest_burst": largest_burst,
        "earliest": timestamps[-1] if timestamps else None,
        "latest": timestamps[0] if timestamps else None,
    }


@mcp.tool()
async def get_certificates(near_expiry_days: int = 30) -> dict:
    """List all stored TLS certificates with expiry status.

    Returns a per-cert summary with `days_until_expiry`, `in_use`, and `expired`
    flags. Designed for monitoring HTTPS / API certs:

      - `expired_in_use`     — certs currently active that have passed expiry
      - `expiring_soon`      — certs currently active expiring within
                               `near_expiry_days` (default 30)
      - `all_certs`          — full list including inactive on-disk certs

    The PEM body and private key are intentionally omitted to keep responses
    compact and to avoid sending sensitive material across MCP transports.
    """
    try:
        return await _check_certs(near_expiry_days=near_expiry_days)
    except Exception as e:
        return _error(f"Failed to get certificates: {_fmt_exc(e)}")


@mcp.tool()
async def get_pf_states() -> dict:
    """Get current pf state-table size and capacity.

    Returns:
      - current / limit / percent_used
      - status: 'ok' | 'high' (>=70%) | 'critical' (>=90%)

    Sustained high utilization can indicate DDoS, NAT exhaustion, or a
    runaway internal client opening connections.
    """
    try:
        st = await _get("/diagnostics/firewall/pf_states")
        if not isinstance(st, dict):
            return _error("Unexpected pf_states response shape")
        current = int(st.get("current", 0) or 0)
        limit = int(st.get("limit", 0) or 0)
        pct = round(current / limit * 100, 2) if limit else None
        if pct is None:
            status = "unknown"
        elif pct >= 90:
            status = "critical"
        elif pct >= 70:
            status = "high"
        else:
            status = "ok"
        return {
            "current": current,
            "limit": limit,
            "percent_used": pct,
            "status": status,
        }
    except Exception as e:
        return _error(f"Failed to get pf states: {_fmt_exc(e)}")


@mcp.tool()
async def get_top_talkers(top_n: int = 10) -> dict:
    """Top bandwidth consumers by interface (LAN + WAN) — useful for spotting
    exfiltration, crypto miners, or runaway uploads.

    Returns the top `top_n` hosts on each interface ranked by total bit rate
    (in + out), each with rate breakdowns and remote-peer detail records.
    """
    try:
        results: dict[str, Any] = {}
        async with _client() as client:
            for iface in ("lan", "wan"):
                try:
                    r = await client.get(f"/diagnostics/traffic/top/{iface}")
                    r.raise_for_status()
                    data = r.json()
                    rows = data.get(iface, {}).get("records", []) if isinstance(data, dict) else []
                    rows.sort(
                        key=lambda x: int(x.get("rate_bits", 0) or 0), reverse=True
                    )
                    results[iface] = [
                        {
                            "address": row.get("address"),
                            "rate_bits": row.get("rate_bits"),
                            "rate_bits_in": row.get("rate_bits_in"),
                            "rate_bits_out": row.get("rate_bits_out"),
                            "cumulative_bytes": row.get("cumulative_bytes"),
                            "tags": row.get("tags", []),
                            "rate_human": row.get("rate"),
                            "details": [
                                {
                                    "address": d.get("address"),
                                    "rate_bits": d.get("rate_bits"),
                                    "cumulative_bytes": d.get("cumulative_bytes"),
                                    "tags": d.get("tags", []),
                                }
                                for d in (row.get("details") or [])[:5]
                            ],
                        }
                        for row in rows[:top_n]
                    ]
                except Exception as e:
                    results[iface] = {"error": _fmt_exc(e)}
        return results
    except Exception as e:
        return _error(f"Failed to get top talkers: {_fmt_exc(e)}")


@mcp.tool()
async def get_recent_config_changes(window_lines: int = 500) -> dict:
    """Recent OPNsense configuration save events.

    Parses the `core/system` log for `config-event: new_config` entries —
    one per config save. Each save creates a backup at
    /conf/backup/config-<epoch>.xml.

    Returns:
      - `count`              — total saves in window
      - `latest_timestamps`  — 10 most recent (full ISO)
      - `hourly_buckets`     — `[{hour, count}, ...]` sorted newest-first,
                               so bursts (admin sessions) are visible as
                               buckets with many saves while steady
                               automation spreads thin across many hours
      - `largest_burst`      — hour with the most saves (or null if none)
      - `earliest` / `latest` — span of the window

    Patterns to watch for: bursts (admin session or scripted churn),
    saves outside maintenance windows, or saves at unusual hours.
    """
    try:
        return await _count_config_changes(window_lines)
    except Exception as e:
        return _error(f"Failed to get config changes: {_fmt_exc(e)}")


@mcp.tool()
async def get_routes() -> dict:
    """Current routing table.

    Useful when WireGuard / Tailscale routes look weird, and as a tamper
    check — unauthorized routes added to a compromised firewall would show
    up here.
    """
    try:
        data = await _get("/diagnostics/interface/getRoutes")
        if isinstance(data, list):
            return {"total": len(data), "routes": data}
        return {"total": 0, "routes": [], "raw": data}
    except Exception as e:
        return _error(f"Failed to get routes: {_fmt_exc(e)}")


if __name__ == "__main__":
    import sys

    transport = "sse" if "--sse" in sys.argv else "stdio"
    mcp.run(transport=transport)
