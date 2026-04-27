# Agent mode — quick start

Multi-server installs run a small agent process on each remote VPN node. The
master panel talks to the agents over HTTP instead of SSH. SSH is only used
once, to install the agent.

This is faster (no SSH round-trip per command) and more reliable on flaky
networks, but it's strictly optional — every agent-mode operation has an SSH
fallback.

## Install the agent on a remote server

From the master, with the server already added to the panel (replace `2` with
the server id):

```bash
curl -X POST http://<panel-host>:10086/api/v1/agent/2/install \
  -H 'Content-Type: application/json' \
  -d '{
    "agent_code_path": "/opt/vpnmanager/agent.py",
    "port": 8001
  }'
```

The installer SSHes into the remote node, uploads `agent.py`, installs the
runtime dependencies (`fastapi`, `uvicorn`, `psutil`), drops a systemd unit,
starts the service, and switches the server's mode to `agent` in the master DB.

## Check status

```bash
curl http://<panel-host>:10086/api/v1/agent/2/status
```

```json
{
  "server_id": 2,
  "server_name": "203.0.113.10",
  "mode": "agent",
  "agent_url": "http://203.0.113.10:8001",
  "agent_healthy": true
}
```

## Switch modes

Switch to agent mode:

```bash
curl -X POST 'http://<panel-host>:10086/api/v1/agent/2/switch-mode?mode=agent'
```

Fall back to SSH (instant, no remote action required):

```bash
curl -X POST 'http://<panel-host>:10086/api/v1/agent/2/switch-mode?mode=ssh'
```

## Verify the agent on the remote node

```bash
ssh root@203.0.113.10
systemctl status vpnmanager-agent
journalctl -u vpnmanager-agent -f
curl http://localhost:8001/health
```

> Existing installs migrated from the legacy `spongebot` build will have the
> service named `spongebot-agent`. Both names are recognised by the master.

## Uninstall

```bash
curl -X POST http://<panel-host>:10086/api/v1/agent/2/uninstall
```

The master switches the server back to SSH mode, stops the agent service on
the remote host, and removes the unit file and `agent.py`.

## Rough numbers

| Operation | SSH mode | Agent mode |
|---|---|---|
| Create client | 2–3s | 0.3s |
| Enable / disable | 2–3s | 0.3s |
| Get stats | 2–3s | 0.3s |

The gap closes for batched calls (an SSH session can be reused) but the
single-call latency is what users actually notice in the admin UI.

## Troubleshooting

If the agent stops responding, switch the server back to SSH mode — that's
non-destructive and takes effect immediately. Then SSH in and inspect the
service:

```bash
ssh root@203.0.113.10 'systemctl status vpnmanager-agent'
ssh root@203.0.113.10 'journalctl -u vpnmanager-agent -n 100'
ssh root@203.0.113.10 'systemctl restart vpnmanager-agent'
```

The agent stores no state of its own — clients, peers, and stats live on the
master. Restarting the agent or reinstalling it from scratch is safe.

## Architecture overview

```
master (203.0.113.1)
  ├─ SSH bootstrap (one-time install)
  └─ HTTP API (ongoing)
       ↓
remote (203.0.113.10)
  └─ agent (FastAPI on :8001)
       └─ runs wg / tc / ip locally
```

For the longer write-up — endpoints, auth, install internals, fallback rules —
see [AGENT_ARCHITECTURE.md](AGENT_ARCHITECTURE.md).
