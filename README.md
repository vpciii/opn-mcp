# opn-mcp

An MCP server for monitoring an OPNsense firewall via its REST API. Primarily read-only with limited, safe write operations.

## Tools

### Status & inventory

| Tool | Description |
|------|-------------|
| `get_system_status` | Firmware version, uptime, CPU, memory, disk, temperature |
| `get_services` | All services with running/stopped state; highlights any stopped daemons |
| `get_updates_available` | Pending OPNsense / package updates (status, packages, reboot needed) |
| `get_interfaces` | All interfaces with status, IP, MAC, traffic counters |
| `get_gateway_status` | Gateways with status, RTT, packet loss |
| `get_dhcp_leases` | Active DHCP leases |
| `get_arp_table` | ARP table entries |

### Security monitoring

| Tool | Description |
|------|-------------|
| `get_security_digest` | **Primary "is anything wrong?" call.** Aggregates failed logins, denied admin actions, firewall blocks, service health, pending updates, certificate expiry, pf state-table utilization, and recent config changes into one compact response with a `warnings` list. |
| `get_auth_events` | Recent UI login attempts (success / failed / denied admin actions) with top source IPs of failures |
| `get_firewall_blocks` | Aggregated pf block events split by WAN-origin (real attack signal) vs LAN-origin (state-table churn); top source IPs, top destination ports |
| `get_certificates` | All TLS certs with `days_until_expiry`, `in_use`, and `expired` flags. Flags expired-in-use and expiring-soon (< 30d). |
| `get_pf_states` | pf state-table size + capacity. Status `ok`/`high` (≥70%) / `critical` (≥90%) for DDoS / NAT-exhaustion detection. |
| `get_top_talkers` | Top bandwidth consumers per interface (LAN/WAN) with peer details — useful for exfiltration / crypto-miner detection. |
| `get_recent_config_changes` | Count + timestamps of `config-event: new_config` saves; flags unauthorized config edits when compared against your own activity. |

### Firewall & NAT

| Tool | Description |
|------|-------------|
| `get_firewall_rules` | All firewall filter rules |
| `get_dnat_rules` | Destination NAT (port-forward) rules |
| `get_snat_rules` | Source NAT (outbound) rules |
| `toggle_dnat_rule` | Enable/disable a DNAT rule by UUID (anti-lockout rules protected) |

### VPN & networking

| Tool | Description |
|------|-------------|
| `get_wireguard_status` | WireGuard instances and peers |
| `get_openvpn_status` | OpenVPN server/client status |
| `get_tailscale_status` | Tailscale plugin service status and settings (requires os-tailscale) |
| `get_unbound_stats` | Unbound DNS resolver statistics |
| `get_routes` | Current routing table (catches unauthorized route additions) |
| `ping_host` | Ping a host from OPNsense |

### Logs

| Tool | Description |
|------|-------------|
| `get_log` | Recent log entries from any source: `firewall` (pf filterlog), `audit`, `configd`, `kernel`, `system`, `resolver`, `routing`, `ipsec`, `openvpn`, `wireguard`, `dhcpd`, etc. Filterable by severity and free-text search. |

## Setup

### 1. Create an OPNsense API Key

1. Log into your OPNsense web UI
2. Go to **System → Access → Users**
3. Edit the user you want to create an API key for (or create a dedicated API user)
4. Scroll to **API keys** and click **+** to create a new key
5. A file will download containing the key and secret — save these securely
6. For read-only access, assign the user to a group with only read/monitoring privileges

### 2. Build the Docker Image

```bash
docker build -t opn-mcp .
```

### 3. Configure Claude Desktop

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "opnsense": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm", "--name", "opn-mcp",
        "-e", "OPNSENSE_HOST=opnsense.example.com",
        "-e", "OPNSENSE_API_KEY=your_key",
        "-e", "OPNSENSE_API_SECRET=your_secret",
        "-e", "OPNSENSE_VERIFY_SSL=true",
        "opn-mcp"
      ]
    }
  }
}
```

Set `OPNSENSE_VERIFY_SSL` to `false` if your OPNsense uses a self-signed certificate.

### Run with SSE Transport (Remote Access)

To run as a persistent service reachable over Tailscale or LAN:

```bash
docker compose up -d
```

This starts the server with SSE transport on port 8000. Connect from Claude Desktop:

```json
{
  "mcpServers": {
    "opnsense": {
      "url": "http://<tailscale-ip-or-hostname>:8000/sse"
    }
  }
}
```

Note: the `docker-compose.yml` uses a `.env` file — copy `.env.example` and fill in your values.

### Run Locally (without Docker)

```bash
pip install .
python server.py
```

Pass `--sse` to use SSE transport instead of stdio.

### Claude Code

```bash
claude mcp add opnsense http://localhost:8000/sse
```

## Hands-off monitoring

The point of `get_security_digest` is to enable autonomous monitoring — a scheduled Claude Code agent that runs the digest on a cron, classifies findings by severity, and pushes notifications to your phone via Home Assistant when something matters.

See **[docs/MONITORING.md](docs/MONITORING.md)** for the full setup: architecture, severity tiers, scheduled-task prompt templates, prerequisites (user-scope MCP, `--init`, permission allow-list), and troubleshooting.

## Notes

- Most tools are **read-only** — the only write operation is `toggle_dnat_rule`, which can enable/disable existing DNAT rules
- Anti-lockout rules are protected and cannot be toggled
- SSL verification is configurable via `OPNSENSE_VERIFY_SSL` (set to `false` for self-signed certs)
- The server defaults to stdio transport (for Claude Desktop via Docker), pass `--sse` for remote access
- Some endpoints may not be available depending on your OPNsense version and installed plugins

## Troubleshooting

### `Invalid port: '<ipv6-fragment>'` on macOS with OrbStack

If you see an httpx `Invalid port` error referencing an IPv6 fragment (e.g. `b51a:cc66:f0::`), it's coming from OrbStack injecting an unbracketed IPv6 CIDR into `NO_PROXY` (its default subnet is `fd07:b51a:cc66:f0::/64`). httpx's URL parser splits on `:` and treats the trailing hex groups as a port.

The server already mitigates this by passing `trust_env=False` to httpx so proxy env vars are ignored — the OPNsense API is on the LAN and shouldn't be proxied anyway. If you still hit this after pulling the latest code, **rebuild the Docker image** so the running container picks up the fix:

```bash
docker build -t opn-mcp .
```

Then restart Claude Desktop (or your MCP host) so the container respawns from the new image.
