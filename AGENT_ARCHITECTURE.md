# Agent architecture

## Overview

The master panel manages remote VPN nodes in one of two modes:

1. **SSH mode** — commands run over SSH each time (the original transport).
2. **Agent mode** — a small FastAPI process on the remote node accepts
   HTTP commands from the master.

SSH is still used to bootstrap the agent (one-shot install). Once the agent
is up, the master switches to HTTP for all subsequent operations. Either
mode can be used at any time per server; a fallback to SSH is always
available.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────┐
│ Master Server (203.0.113.1)                   │
│                                                  │
│  ┌────────────────────────────────────────────┐ │
│  │ Web Panel + API                            │ │
│  │ PostgreSQL (clients, servers DB)           │ │
│  │ Local WireGuard (wg0)                      │ │
│  └────────────────────────────────────────────┘ │
│                                                  │
│  ┌────────────────────────────────────────────┐ │
│  │ ServerManager                              │ │
│  │   ├─ _get_wg() → RemoteServerAdapter      │ │
│  │   ├─ install_agent() [uses SSH bootstrap] │ │
│  │   └─ switch_mode()                         │ │
│  └────────────────────────────────────────────┘ │
│                                                  │
│  ┌────────────────┐     ┌───────────────────┐  │
│  │ SSH Bootstrap  │     │ RemoteAdapter     │  │
│  │ (one-time      │     │ ├─ agent mode     │  │
│  │  install)      │     │ │  → AgentClient  │  │
│  │                │     │ └─ ssh mode       │  │
│  │                │     │    → WireGuard    │  │
│  │                │     │       Manager     │  │
│  └────────────────┘     └───────────────────┘  │
└──────────┬──────────────────┬───────────────────┘
           │                  │
           │ SSH (once)       │ HTTP API (ongoing)
           │                  │
    ┌──────┴──────┐    ┌──────┴──────┐
    │             │    │             │
    v             v    v             v
┌─────────┐  ┌─────────┐  ┌─────────┐
│ Remote  │  │ Remote  │  │ Remote  │
│ Server 1│  │ Server 2│  │ Server N│
│         │  │         │  │         │
│ Agent   │  │ Agent   │  │ SSH     │
│ (HTTP)  │  │ (HTTP)  │  │ (legacy)│
└─────────┘  └─────────┘  └─────────┘
```

---

## Components

### 1. Agent (on child server)

**File:** `agent.py`

**Stack:**
- FastAPI (HTTP API)
- Local copy of WireGuardManager (NO SSH)
- Executes `wg`, `tc`, `ip` commands locally

**Endpoints:**
- `POST /peer/create` - add peer to WireGuard
- `POST /peer/delete` - remove peer
- `POST /peer/enable` - enable peer
- `POST /peer/disable` - disable peer
- `POST /peer/set_bandwidth` - set tc bandwidth limit
- `GET /stats` - get interface + peers stats
- `GET /health` - health check

**Auth:** API key in `X-API-Key` header

**Systemd:** `vpnmanager-agent.service`

**Environment:**
```bash
AGENT_API_KEY=<generated_key>
WG_INTERFACE=wg0
WG_CONFIG_PATH=/etc/wireguard/wg0.conf
AGENT_PORT=8001
```

### 2. AgentBootstrap (on master)

**File:** `src/core/agent_bootstrap.py`

**Purpose:** One-time agent installation via SSH

**Process:**
1. SSH connect to remote server
2. Create `/opt/vpnmanager-agent/` directory
3. Upload `agent.py` via SFTP
4. Install Python dependencies (`pip3 install fastapi uvicorn psutil`)
5. Create systemd service with generated API key
6. Enable and start service
7. Return `(success, agent_url, api_key)`

**Methods:**
- `install_agent()` - install agent on remote server
- `uninstall_agent()` - remove agent
- `check_agent_health()` - verify agent is running

### 3. AgentClient (on master)

**File:** `src/core/agent_client.py`

**Purpose:** HTTP client for Agent API

**Methods:**
- `create_peer(public_key, allowed_ips, preshared_key)`
- `delete_peer(public_key)`
- `enable_peer(public_key, allowed_ips, preshared_key)`
- `disable_peer(public_key)`
- `set_bandwidth(ip, limit_mbps)`
- `get_stats()` - get interface + peers stats
- `health_check()` - ping agent

### 4. RemoteServerAdapter (on master)

**File:** `src/core/remote_adapter.py`

**Purpose:** Route commands to SSH or Agent based on `server.agent_mode`

**Interface:** Same as WireGuardManager (NO breaking changes)

**Routing logic:**
```python
if server.agent_mode == "agent":
    # Use HTTP API
    backend = AgentClient(server.agent_url, server.agent_api_key)
else:
    # Use SSH (existing code)
    backend = WireGuardManager(ssh_host=..., ssh_port=...)
```

**Methods:**
- `add_peer()` → routes to `agent.create_peer()` or `wg.add_peer()`
- `remove_peer()` → routes to `agent.delete_peer()` or `wg.remove_peer()`
- `get_stats()` → routes to `agent.get_stats()` or `wg.get_interface_info()`
- All other WireGuardManager methods...

### 5. ServerManager Patch

**File:** `src/core/server_manager.py`

**Changes:**

```python
def _get_wg(self, server):
    """Return RemoteServerAdapter for remote servers"""
    if not server.ssh_host:
        # Local server - direct WireGuardManager
        return WireGuardManager(interface=server.interface)
    else:
        # Remote server - use adapter (routes to SSH or Agent)
        return RemoteServerAdapter(server, server.interface)
```

**New methods:**
- `install_agent(server_id)` - install agent via SSH
- `uninstall_agent(server_id)` - remove agent
- `switch_to_agent_mode(server_id)` - switch to HTTP API
- `switch_to_ssh_mode(server_id)` - fallback to SSH

### 6. Database Schema

**Server model additions:**

```python
agent_mode: str = "ssh"  # "ssh" or "agent"
agent_url: Optional[str] = None  # "http://203.0.113.10:8001"
agent_api_key: Optional[str] = None
```

**Migration:** Auto-adds columns on startup

### 7. API Endpoints

**File:** `src/api/routes/agent.py`

- `POST /api/v1/agent/{server_id}/install` - install agent
- `POST /api/v1/agent/{server_id}/uninstall` - uninstall agent
- `POST /api/v1/agent/{server_id}/switch-mode` - switch mode
- `GET /api/v1/agent/{server_id}/status` - get agent status

---

## Usage Flow

### Install Agent on Remote Server

```bash
# 1. Server already registered with SSH access
POST /api/v1/servers
{
  "name": "Amsterdam",
  "ssh_host": "203.0.113.10",
  "ssh_user": "root",
  "ssh_password": "***",
  ...
}

# 2. Install agent (uses SSH bootstrap)
POST /api/v1/agent/2/install
{
  "agent_code_path": "/opt/vpnmanager/agent.py",
  "port": 8001
}

# Response:
{
  "success": true,
  "agent_url": "http://203.0.113.10:8001",
  "mode": "agent"
}

# 3. Now all operations use HTTP API instead of SSH
POST /api/v1/clients
{
  "name": "test_client",
  "server_id": 2  # Uses agent mode
}
```

### Switch Between Modes

```bash
# Switch to agent mode (if agent installed)
POST /api/v1/agent/2/switch-mode?mode=agent

# Fallback to SSH mode (legacy)
POST /api/v1/agent/2/switch-mode?mode=ssh
```

### Check Agent Status

```bash
GET /api/v1/agent/2/status

# Response:
{
  "server_id": 2,
  "server_name": "Amsterdam",
  "mode": "agent",
  "agent_url": "http://203.0.113.10:8001",
  "agent_healthy": true
}
```

---

## Performance Comparison

| Operation | SSH Mode | Agent Mode |
|-----------|----------|------------|
| Create client | ~2-3s (SSH handshake + wg set) | ~0.3s (HTTP POST) |
| Delete client | ~2-3s | ~0.3s |
| Get stats | ~2-3s (first) / 0.2s (cached) | ~0.3s |
| Bandwidth limit | ~2-3s | ~0.3s |

Agent mode is **~10x faster** because:
- No SSH handshake overhead
- Persistent HTTP connection
- Local command execution

---

## Migration Strategy

### Phase 1: Install agents (SSH for bootstrap)
```bash
for server_id in [2, 3]:
    POST /api/v1/agent/{server_id}/install
```

### Phase 2: Verify all working
```bash
# Create test client on each server
# Verify stats, enable/disable work
```

### Phase 3: Switch to agent mode
```bash
for server_id in [2, 3]:
    POST /api/v1/agent/{server_id}/switch-mode?mode=agent
```

### Phase 4: Monitor
- Check agent health: `GET /api/v1/agent/{id}/status`
- If issues: `switch-mode?mode=ssh` (instant rollback)

---

## Emergency Procedures

### Agent Down - Rollback to SSH

```bash
# Instant fallback (no downtime)
POST /api/v1/agent/{server_id}/switch-mode?mode=ssh
```

### Agent Restart

```bash
# On child server
systemctl restart vpnmanager-agent
systemctl status vpnmanager-agent
```

### Agent Logs

```bash
# On child server
journalctl -u vpnmanager-agent -f
```

### Agent Uninstall

```bash
# Via API (uses SSH)
POST /api/v1/agent/{server_id}/uninstall

# Or manually on child server
systemctl stop vpnmanager-agent
systemctl disable vpnmanager-agent
rm -rf /opt/vpnmanager-agent
rm /etc/systemd/system/vpnmanager-agent.service
systemctl daemon-reload
```

---

## Security

### API Key
- Generated during install: `secrets.token_urlsafe(32)`
- Stored in server DB (encrypted TODO)
- Passed in `X-API-Key` header

### Network
- Agent listens on `0.0.0.0:8001`
- **TODO:** Add firewall rules (only allow master IP)
- **TODO:** Add HTTPS/TLS support

### Agent Process
- Runs as `root` (required for `wg`, `tc` commands)
- No shell access
- Only predefined API endpoints

---

## Compatibility

### Existing Code - NO CHANGES

- `ClientManager` - unchanged, calls same methods
- `TrafficManager` - unchanged
- `TimerManager` - unchanged
- All managers use `ServerManager._get_wg()` which now returns `RemoteServerAdapter`

### RemoteServerAdapter Interface

100% compatible with `WireGuardManager`:
```python
# Before (direct WireGuardManager)
wg = WireGuardManager(ssh_host="...", ...)
wg.add_peer(public_key, allowed_ips)

# After (RemoteServerAdapter routes to agent or SSH)
adapter = RemoteServerAdapter(server, interface)
adapter.add_peer(public_key, allowed_ips)  # Same interface!
```

---

## Testing

### Manual Test

```bash
# 1. Install agent
curl -X POST http://203.0.113.1:10086/api/v1/agent/2/install \
  -H "Content-Type: application/json" \
  -d '{"agent_code_path": "/opt/vpnmanager/agent.py", "port": 8001}'

# 2. Create client (should use agent)
curl -X POST http://203.0.113.1:10086/api/v1/clients \
  -H "Content-Type: application/json" \
  -d '{"name": "test", "server_id": 2}'

# 3. Verify on child server
ssh root@203.0.113.10 "wg show"

# 4. Check agent logs
ssh root@203.0.113.10 "journalctl -u vpnmanager-agent -n 20"
```

---

## TODOs

- [ ] Encrypt agent_api_key in database
- [ ] Add HTTPS/TLS support for agent
- [ ] Add firewall rules on child servers
- [ ] Add metrics/monitoring for agents
- [ ] Add auto-restart on agent failure
- [ ] Add agent version check/upgrade mechanism
- [ ] Add config sync (master → agent)

---

## Summary

✅ **SSH code preserved** - used only for bootstrap
✅ **Agent mode** - HTTP API for ongoing management
✅ **Backward compatible** - existing managers unchanged
✅ **Instant fallback** - switch to SSH if agent fails
✅ **10x faster** - no SSH overhead
✅ **Easy migration** - one API call to install agent
