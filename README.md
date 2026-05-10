# opn-mcp

An MCP server for monitoring an OPNsense firewall via its REST API. Primarily read-only with limited, safe write operations.

## Tools

| Tool | Description |
|------|-------------|
| `get_system_status` | Firmware version, uptime, CPU, memory, disk, temperature |
| `get_interfaces` | All interfaces with status, IP, MAC, traffic counters |
| `get_gateway_status` | Gateways with status, RTT, packet loss |
| `get_dhcp_leases` | Active DHCP leases |
| `get_firewall_rules` | All firewall filter rules |
| `get_log` | Recent log entries from any source: `firewall` (pf rule hits), `audit`, `configd`, `kernel`, `resolver`, `routing`, `ipsec`, `openvpn`, `wireguard`, `dhcpd`, etc. Filterable by severity and free-text search. |
| `get_dnat_rules` | Destination NAT (port-forward) rules |
| `get_snat_rules` | Source NAT (outbound) rules |
| `toggle_dnat_rule` | Enable/disable a DNAT rule by UUID (anti-lockout rules protected) |
| `get_wireguard_status` | WireGuard instances and peers |
| `get_arp_table` | ARP table entries |
| `get_unbound_stats` | Unbound DNS resolver statistics |
| `ping_host` | Ping a host from OPNsense |
| `get_openvpn_status` | OpenVPN server/client status |
| `get_tailscale_status` | Tailscale plugin service status and settings (requires os-tailscale) |

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
