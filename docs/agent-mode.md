# Agent Mode

The VPN Manager agent is a lightweight FastAPI process that runs on each remote server. It provides a local HTTP API for WireGuard management, replacing the need for ongoing SSH connections.

---

## Why an Agent

SSH is used only once — to install the agent. After that:

- All peer operations (add, remove, enable, disable) go through the agent's HTTP API
- No open SSH session is needed for normal operation
- The agent executes `wg`, `awg`, `tc`, and `ip` commands locally with full privileges
- Each operation completes in under 100ms vs 1–3 seconds over SSH

---

## How the Agent Is Installed

When you click **Install Agent** on a server in the admin panel, the bootstrap process runs automatically:

1. SSH connect to the remote server
2. Check that WireGuard (or AmneziaWG) tools are present — fail early if not
3. Create `/opt/vpnmanager-agent/` directory
4. Upload `agent.py` via SFTP
5. Create a Python virtual environment at `/opt/vpnmanager-agent/venv/`
6. Install dependencies (`fastapi`, `uvicorn`, `httpx`)
7. Generate an API key and write `/opt/vpnmanager-agent/.env`
8. Create and enable a systemd service (`vpnmanager-agent`)
9. If the WireGuard interface is not yet configured: write the server config and run `wg-quick up`
10. Verify the agent is responding on port 8001

The bootstrap is **idempotent** — running it again on a server that already has the agent updates the agent binary and restarts the service without reconfiguring WireGuard.

---

## Agent Endpoints

The agent exposes these endpoints. All requests require the `X-Api-Key` header.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check — returns interface status and peer count |
| `GET` | `/stats` | Interface and per-peer traffic statistics |
| `GET` | `/peers` | List all current peers with allowed IPs |
| `POST` | `/peer/create` | Add a peer to the WireGuard interface |
| `POST` | `/peer/delete` | Remove a peer |
| `POST` | `/peer/enable` | Re-add a disabled peer |
| `POST` | `/peer/disable` | Remove a peer from the interface (keeps DB record) |
| `POST` | `/peer/set_bandwidth` | Apply `tc` bandwidth limit to a peer |

### Example: Health Check

```bash
curl -H "X-Api-Key: your-api-key" http://remote-server:8001/health
```

Response:

```json
{
  "status": "ok",
  "interface": "wg0",
  "peers": 12,
  "version": "1.4.11"
}
```

### Example: Add a Peer

```bash
curl -X POST \
  -H "X-Api-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"public_key":"abc123==","allowed_ips":["10.66.66.5/32"]}' \
  http://remote-server:8001/peer/create
```

---

## Agent Configuration

The agent reads its configuration from `/opt/vpnmanager-agent/.env`:

| Variable | Description |
|----------|-------------|
| `AGENT_API_KEY` | Secret key for request authentication |
| `WG_INTERFACE` | WireGuard interface name (`wg0`, `awg0`) |
| `WG_CONFIG_PATH` | Path to the WireGuard config file |
| `AGENT_PORT` | HTTP port (default: 8001) |

For AmneziaWG servers, the agent uses `awg` / `awg-quick` instead of `wg` / `wg-quick`. The interface name determines which tool set is used.

---

## Checking Agent Status

On the remote server:

```bash
# Service status
systemctl status vpnmanager-agent

# Live logs
journalctl -u vpnmanager-agent -f

# Manual health check
curl -H "X-Api-Key: $(grep AGENT_API_KEY /opt/vpnmanager-agent/.env | cut -d= -f2)" \
  http://localhost:8001/health
```

From the main server (admin panel):

- Go to **Servers** and look at the status badge
- Click **Refresh** on a server card to run an immediate health check
- Go to **Server Monitoring** for live stats

---

## Security

- The agent API key is generated with `secrets.token_hex(32)` during bootstrap
- The key is stored in `/opt/vpnmanager-agent/.env` (mode 600) on the remote server
- The same key is stored in the database on the main server (encrypted at rest)
- All requests are rejected if the key is missing or wrong (HTTP 401)
- The agent has no outbound connections — it only accepts inbound requests

**Firewall recommendation:** restrict port 8001 to the main server's IP only.

```bash
# Example: allow only the main server
ufw allow from MAIN_SERVER_IP to any port 8001
ufw deny 8001
```

---

## Reinstalling the Agent

If the agent is broken or the server was reconfigured:

1. In the admin panel, go to **Servers → {server name} → Agent**
2. Click **Reinstall Agent**

Or use the API:

```bash
POST /api/v1/servers/{id}/install-agent
```

The bootstrap is idempotent — existing WireGuard config is not touched unless the interface is down.

---

## Uninstalling the Agent

```bash
# On the remote server
systemctl disable --now vpnmanager-agent
rm -rf /opt/vpnmanager-agent
rm /etc/systemd/system/vpnmanager-agent.service
systemctl daemon-reload
```

After uninstalling, either switch the server in the admin panel back to **SSH mode** or delete the server record.

---

## SSH Mode (Legacy)

If agent installation fails or you want to operate without an agent, SSH mode is available. In SSH mode, every WireGuard operation opens an SSH session, runs a command, and closes the connection.

SSH mode is reliable but slower (1–3 seconds per operation). It is suitable for low-traffic servers or as a fallback.

To switch between modes: **Servers → {server name} → Connection Mode → SSH / Agent**.

The SSH credentials you entered during server setup are kept in the database (encrypted) and are used both for bootstrap and for ongoing SSH operations in SSH mode.
