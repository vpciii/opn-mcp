# opn-mcp

A read-only MCP server for monitoring an OPNsense firewall via its REST API.

## Tools

| Tool | Description |
|------|-------------|
| `get_system_status` | Firmware version, uptime, CPU, memory, disk, temperature |
| `get_interfaces` | All interfaces with status, IP, MAC, traffic counters |
| `get_gateway_status` | Gateways with status, RTT, packet loss |
| `get_dhcp_leases` | Active DHCP leases |
| `get_firewall_logs` | Recent firewall log entries (filterable by interface/limit) |
| `get_wireguard_status` | WireGuard instances and peers |
| `get_arp_table` | ARP table entries |
| `get_unbound_stats` | Unbound DNS resolver statistics |
| `ping_host` | Ping a host from OPNsense |
| `get_openvpn_status` | OpenVPN server/client status |

## Setup

### 1. Create an OPNsense API Key

1. Log into your OPNsense web UI
2. Go to **System → Access → Users**
3. Edit the user you want to create an API key for (or create a dedicated API user)
4. Scroll to **API keys** and click **+** to create a new key
5. A file will download containing the key and secret — save these securely
6. For read-only access, assign the user to a group with only read/monitoring privileges

### 2. Configure Environment

Copy the example env file and fill in your values:

```bash
cp .env.example .env
```

Edit `.env`:

```
OPNSENSE_HOST=192.168.1.1
OPNSENSE_API_KEY=your_key
OPNSENSE_API_SECRET=your_secret
OPNSENSE_VERIFY_SSL=false
```

### 3. Run with Docker

```bash
docker compose up -d
```

The server will be available at `http://localhost:8000/sse`.

### 4. Run Locally (without Docker)

```bash
pip install .
python server.py
```

## MCP Client Configuration

### Claude Desktop

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "opnsense": {
      "command": "python",
      "args": ["/path/to/opn-mcp/server.py"],
      "env": {
        "OPNSENSE_HOST": "192.168.1.1",
        "OPNSENSE_API_KEY": "your_key",
        "OPNSENSE_API_SECRET": "your_secret",
        "OPNSENSE_VERIFY_SSL": "false"
      }
    }
  }
}
```

### Claude Desktop (remote via Docker/Tailscale)

If running the server on another machine reachable over Tailscale or LAN:

```json
{
  "mcpServers": {
    "opnsense": {
      "url": "http://<tailscale-ip-or-hostname>:8000/sse"
    }
  }
}
```

### Claude Code

```bash
claude mcp add opnsense http://localhost:8000/sse
```

Or for a remote instance:

```bash
claude mcp add opnsense http://<tailscale-ip-or-hostname>:8000/sse
```

### claude.ai (Remote MCP)

Use the SSE URL directly: `http://<your-host>:8000/sse`

## Notes

- All tools are **read-only** — no configuration changes are made to OPNsense
- SSL verification is disabled by default since most OPNsense installations use self-signed certificates
- The server uses SSE transport by default, suitable for remote access over Tailscale/LAN
- Some endpoints may not be available depending on your OPNsense version and installed plugins
