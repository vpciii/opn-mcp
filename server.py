"""MCP server for read-only OPNsense firewall monitoring."""

import os
import ssl

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
                results["firmware"] = _error(str(e))

            # System resources via activity endpoint
            try:
                r = await client.get("/diagnostics/activity/getActivity")
                r.raise_for_status()
                activity = r.json()
                headers = activity.get("headers", "")
                results["activity_summary"] = headers
            except Exception as e:
                results["activity"] = _error(str(e))

            # System info (uptime, etc.)
            try:
                r = await client.get("/diagnostics/system/system_information")
                r.raise_for_status()
                results["system_info"] = r.json()
            except Exception as e:
                results["system_info"] = _error(str(e))

            # Temperature (HAProxy health or system temps)
            try:
                r = await client.get("/diagnostics/system/system_temperature")
                r.raise_for_status()
                results["temperature"] = r.json()
            except Exception:
                results["temperature"] = "not available"

        return results
    except Exception as e:
        return _error(f"Failed to get system status: {e}")


@mcp.tool()
async def get_interfaces() -> dict:
    """Get all network interfaces with name, status, IP address, MAC address, and traffic counters."""
    try:
        data = await _get("/diagnostics/interface/getInterfaceStatistics")
        return data
    except Exception as e:
        return _error(f"Failed to get interfaces: {e}")


@mcp.tool()
async def get_gateway_status() -> dict:
    """Get all gateways with name, IP, status, RTT, and packet loss."""
    try:
        data = await _post("/routes/gateway/status")
        return data
    except Exception as e:
        return _error(f"Failed to get gateway status: {e}")


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
        return _error(f"Failed to get DHCP leases: {e}")


LOG_SOURCES = {
    "firewall": "pf/filter",
    "firewall_subsys": "pf/firewall",
    "audit": "core/audit",
    "configd": "core/configd",
    "kernel": "core/kernel",
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


@mcp.tool()
async def get_log(
    source: str = "firewall",
    limit: int = 50,
    severity: str = "",
    search: str = "",
) -> dict:
    """Get recent OPNsense log entries.

    Source aliases: 'firewall' (pf/filter rule hits), 'firewall_subsys', 'audit',
    'configd', 'kernel', 'resolver', 'routing', 'wireless', 'lighttpd', 'pkg',
    'ipsec', 'openvpn', 'wireguard', 'ntpd', 'monit', 'captiveportal', 'dnsmasq',
    'dhcpd'. Alternatively pass a raw 'module/scope' path (e.g. 'pf/filter').

    Optional: severity (e.g. 'Error', 'Warning', 'Notice', 'Informational'),
    search (free-text phrase).
    """
    try:
        path = LOG_SOURCES.get(source, source)
        if path.count("/") != 1:
            return _error(
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
    except Exception as e:
        return _error(f"Failed to get '{source}' log: {e}")


@mcp.tool()
async def get_wireguard_status() -> dict:
    """Get WireGuard VPN instances and peer connection status."""
    try:
        data = await _get("/wireguard/service/show")
        return data
    except Exception as e:
        return _error(f"Failed to get WireGuard status: {e}")


@mcp.tool()
async def get_arp_table() -> dict:
    """Get the current ARP table with IP, MAC address, interface, and hostname."""
    try:
        data = await _get("/diagnostics/interface/getArp")
        return data
    except Exception as e:
        return _error(f"Failed to get ARP table: {e}")


@mcp.tool()
async def get_unbound_stats() -> dict:
    """Get Unbound DNS resolver statistics including cache hits, misses, and query counts."""
    try:
        data = await _post("/unbound/service/dnsStats")
        return data
    except Exception as e:
        return _error(f"Failed to get Unbound stats: {e}")


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
        return _error(f"Failed to ping {target}: {e}")


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
                results["sessions"] = _error(str(e))

            # OpenVPN instances
            try:
                r = await client.get("/openvpn/instances/search")
                r.raise_for_status()
                results["instances"] = r.json()
            except Exception as e:
                results["instances"] = _error(str(e))

        return results
    except Exception as e:
        return _error(f"Failed to get OpenVPN status: {e}")


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
                results["service"] = _error(str(e))

            try:
                r = await client.get("/tailscale/settings/get")
                r.raise_for_status()
                results["settings"] = r.json()
            except Exception as e:
                results["settings"] = _error(str(e))

        return results
    except Exception as e:
        return _error(f"Failed to get Tailscale status: {e}")


@mcp.tool()
async def get_firewall_rules() -> dict:
    """Get all firewall filter rules with source, destination, port, protocol, action, and status."""
    try:
        data = await _get("/firewall/filter/searchRule")
        return data
    except Exception as e:
        return _error(f"Failed to get firewall rules: {e}")


@mcp.tool()
async def get_dnat_rules() -> dict:
    """Get all Destination NAT (port-forward) rules with source, destination, ports, and target."""
    try:
        data = await _get("/firewall/d_nat/searchRule")
        return data
    except Exception as e:
        return _error(f"Failed to get DNAT rules: {e}")


@mcp.tool()
async def get_snat_rules() -> dict:
    """Get all Source NAT (outbound) rules."""
    try:
        data = await _get("/firewall/source_nat/searchRule")
        return data
    except Exception as e:
        return _error(f"Failed to get SNAT rules: {e}")


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
        return _error(f"Failed to toggle DNAT rule: {e}")


if __name__ == "__main__":
    import sys

    transport = "sse" if "--sse" in sys.argv else "stdio"
    mcp.run(transport=transport)
