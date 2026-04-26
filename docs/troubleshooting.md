# Troubleshooting

---

## API Not Starting

**Symptom:** The admin panel is unreachable. `systemctl status vpnmanager-api` shows `failed`.

**Check logs:**

```bash
journalctl -u vpnmanager-api -n 50 --no-pager
```

**Common causes:**

| Error in logs | Fix |
|---------------|-----|
| `connection refused` on port 5432 | PostgreSQL is not running: `systemctl start postgresql` |
| `password authentication failed` | `DATABASE_URL` in `.env` has wrong credentials |
| `port 10086 already in use` | Another process is using the port: `ss -tlnp \| grep 10086` |
| `ModuleNotFoundError` | Virtual environment is broken: `cd /opt/vpnmanager && venv/bin/pip install -r requirements.txt` |

---

## Database Connection Error

```bash
# Check PostgreSQL status
systemctl status postgresql

# Check the connection string
grep DATABASE_URL /opt/vpnmanager/.env

# Test connection manually
psql "$(grep DATABASE_URL /opt/vpnmanager/.env | cut -d= -f2-)"
```

If the database user or name is wrong, recreate it:

```bash
sudo -u postgres psql << 'SQL'
CREATE USER vpnmanager WITH PASSWORD 'your-password';
CREATE DATABASE vpnmanager_db OWNER vpnmanager;
SQL
```

---

## WireGuard Interface Not Working

**Interface down:**

```bash
sudo wg show
sudo systemctl status wg-quick@wg0

# Bring up manually
sudo wg-quick up wg0
```

**IP forwarding disabled:**

```bash
sysctl net.ipv4.ip_forward
# Should be 1. If not:
echo "net.ipv4.ip_forward = 1" >> /etc/sysctl.conf
sysctl -p
```

**NAT rules missing:**

```bash
iptables -t nat -L POSTROUTING -n -v
```

If the MASQUERADE rule is missing, it means `wg-quick up` did not apply the PostUp rules. Restart the interface:

```bash
sudo wg-quick down wg0
sudo wg-quick up wg0
```

**Peer not receiving traffic:**

```bash
# Check peer is in the interface
sudo wg show wg0

# Check latest handshake
sudo wg show wg0 latest-handshakes
```

A peer that has never handshaked has never connected. Verify:
- The client config has the correct server public key and endpoint
- The server endpoint is reachable (UDP, not TCP — check firewall)
- The client IP matches what is in `AllowedIPs` on the server

---

## AmneziaWG Problems

**`awg: command not found`:**

```bash
# Check if module is installed
lsmod | grep amneziawg

# Install amneziawg-dkms
apt install amneziawg-dkms
```

**Interface not starting:**

```bash
sudo awg show
sudo awg-quick up awg0
journalctl -u wg-quick@awg0 -n 20
```

**Clients can connect but no internet:**

```bash
# Check route exists for the client subnet
ip route show | grep awg0

# Add manually if missing (replace with your actual subnet)
ip route add 10.9.0.0/24 dev awg0
```

**Client uses wrong H values:**
If clients get stale configs with incorrect obfuscation parameters, have them re-download the config from the admin panel or client portal. Old configs with mismatched H values will fail to establish a connection.

---

## Agent Problems

**Agent not responding:**

```bash
# On the remote server
systemctl status vpnmanager-agent
journalctl -u vpnmanager-agent -n 30 --no-pager

# Test manually
curl -H "X-Api-Key: $(grep AGENT_API_KEY /opt/vpnmanager-agent/.env | cut -d= -f2)" \
  http://localhost:8001/health
```

**Wrong API key:**

The API key in the agent's `.env` on the remote server must match the key stored on the main server. If they differ, reinstall the agent:
- Admin panel → **Servers → {server} → Install Agent**

**Agent installed but main server can't reach it:**

```bash
# Check port is open on the remote server
ss -tlnp | grep 8001

# From the main server
curl -H "X-Api-Key: key" http://REMOTE_IP:8001/health
```

Firewall on the remote server may be blocking port 8001. Allow only the main server:

```bash
ufw allow from MAIN_SERVER_IP to any port 8001
```

**Bootstrap fails at "AWG not found":**

The AmneziaWG tools must be installed before the agent can be bootstrapped on an AmneziaWG server. The bootstrap checks for `awg` in `PATH` and returns an error if it is not found. Install AmneziaWG on the remote server first.

---

## SSH Connection Problems

**`Connection refused` or timeout:**

```bash
# Test SSH from the main server
ssh -i /path/to/key -p PORT root@REMOTE_IP

# Check SSH service on remote server
systemctl status sshd
```

**`Host key verification failed`:**

The remote server's host key changed (server was rebuilt). Remove the stale entry:

```bash
ssh-keygen -R REMOTE_IP
```

**Permission denied (publickey):**

The SSH private key in the server record does not match the `authorized_keys` on the remote server. Update the SSH credentials in **Servers → Edit**.

---

## Ports and Firewall

Default ports that must be accessible:

| Port | Protocol | Service |
|------|----------|---------|
| 10086 | TCP | Admin panel |
| 10090 | TCP | Client portal |
| 51820 | UDP | WireGuard (local server default) |
| 8001 | TCP | Agent (remote servers, from main server only) |

Check firewall:

```bash
ufw status verbose
# or
iptables -L -n -v
```

---

## Telegram Bot Not Responding

```bash
journalctl -u vpnmanager-admin-bot -n 50 --no-pager
```

**Common issues:**

- Wrong bot token — verify with @BotFather
- Your Telegram user ID is not in `ADMIN_BOT_ALLOWED_USERS`
- The bot service crashed — check logs, then restart:
  ```bash
  systemctl restart vpnmanager-admin-bot
  ```

---

## Client Portal Blank Page or Errors

```bash
journalctl -u vpnmanager-client-portal -n 50 --no-pager
```

- Verify `SERVICE_API_TOKEN` in `.env` matches between the API and client portal services
- Check that `vpnmanager-api` is running — the portal depends on the API

---

## Subscriptions Not Expiring

The background worker handles subscription expiry. If subscriptions are not expiring:

```bash
systemctl status vpnmanager-worker
```

- The worker must be running
- `WORKER_ENABLED=true` must be set in `.env`

If the worker is not installed, the API handles background tasks internally, but this is less reliable under load.

---

## License Issues

**"License validation failed":**
- Check `Settings → License` for the current status
- Verify your server has internet access to reach the license server
- Grace period is 72 hours — the system continues working without internet for up to 72 hours

**"Activation required":**
- The license key does not match this server's ID
- Get your Server ID from `Settings → License` and contact your vendor

---

## Verify Installation

```bash
cd /opt/vpnmanager
source venv/bin/activate
python3 -c "from src.api.main import app; print(f'{len(app.routes)} routes loaded')"
```

Expected output: a number like `85 routes loaded`. Any import error points to a missing dependency or broken environment.

---

## Collect Diagnostic Information for Support

```bash
echo "=== OS ===" && cat /etc/os-release
echo "=== Python ===" && python3 --version
echo "=== Services ===" && systemctl is-active vpnmanager-api vpnmanager-worker wg-quick@wg0
echo "=== WireGuard ===" && wg show 2>/dev/null || echo "not running"
echo "=== API logs ===" && journalctl -u vpnmanager-api -n 30 --no-pager
echo "=== Server ID ===" && grep ACTIVATION_CODE /opt/vpnmanager/.env 2>/dev/null || echo "check Settings > License"
```

Include this output when contacting support.
