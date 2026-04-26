# Agent Mode - Quick Start

## Install Agent on Remote Server (One Command)

```bash
curl -X POST http://203.0.113.1:10086/api/v1/agent/2/install \
  -H "Content-Type: application/json" \
  -d '{
    "agent_code_path": "/opt/vpnmanager/agent.py",
    "port": 8001
  }'
```

**What happens:**
1. SSH connects to remote server
2. Uploads agent.py
3. Installs dependencies (fastapi, uvicorn, psutil)
4. Creates systemd service
5. Starts agent
6. Switches server to agent mode

**Result:**
- All future operations use HTTP API (10x faster)
- SSH only used for install (one time)

---

## Check Agent Status

```bash
curl http://203.0.113.1:10086/api/v1/agent/2/status
```

**Response:**
```json
{
  "server_id": 2,
  "server_name": "203.0.113.10",
  "mode": "agent",
  "agent_url": "http://203.0.113.10:8001",
  "agent_healthy": true
}
```

---

## Switch Modes

### Switch to Agent Mode
```bash
curl -X POST "http://203.0.113.1:10086/api/v1/agent/2/switch-mode?mode=agent"
```

### Fallback to SSH Mode (instant)
```bash
curl -X POST "http://203.0.113.1:10086/api/v1/agent/2/switch-mode?mode=ssh"
```

---

## Verify Agent on Child Server

```bash
ssh root@203.0.113.10

# Check service
systemctl status spongebot-agent

# Check logs
journalctl -u spongebot-agent -f

# Test agent health
curl http://localhost:8001/health
```

---

## Uninstall Agent

```bash
curl -X POST http://203.0.113.1:10086/api/v1/agent/2/uninstall
```

---

## Performance

| Operation | SSH Mode | Agent Mode |
|-----------|----------|------------|
| Create client | 2-3s | 0.3s ⚡ |
| Enable/Disable | 2-3s | 0.3s ⚡ |
| Get stats | 2-3s | 0.3s ⚡ |

**Agent = 10x faster!**

---

## Troubleshooting

### Agent not responding

```bash
# Switch to SSH mode (instant fallback)
curl -X POST "http://203.0.113.1:10086/api/v1/agent/2/switch-mode?mode=ssh"
```

### Restart agent on child server

```bash
ssh root@203.0.113.10 "systemctl restart spongebot-agent"
```

### Check agent logs

```bash
ssh root@203.0.113.10 "journalctl -u spongebot-agent -n 50"
```

---

## Architecture

```
Master (203.0.113.1)
  ├─ SSH Bootstrap (one-time install)
  └─ HTTP API calls (ongoing)
          ↓
Child (203.0.113.10)
  └─ Agent (FastAPI)
      ├─ Listens on :8001
      └─ Executes wg/tc commands locally
```

**Key Points:**
- ✅ Existing SSH code preserved
- ✅ Agent mode is optional (fallback to SSH anytime)
- ✅ No changes to ClientManager, TrafficManager
- ✅ 10x performance improvement
- ✅ Instant rollback if issues

See [AGENT_ARCHITECTURE.md](AGENT_ARCHITECTURE.md) for full details.
