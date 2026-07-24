# Adding Servers

_Last verified: 2026-07-24._

Flirexa can manage WireGuard on multiple servers. The local server is registered automatically during installation. Additional remote servers are added through the admin panel.

> **Paid feature.** Multi-server orchestration and the remote agent are a
> **Business-tier** capability. On FREE, one install host can run one WireGuard
> and one AmneziaWG endpoint. The working agent implementation is delivered
> separately; similarly named files in this public repository are API-contract
> stubs, not a standalone agent distribution.

---

## How Remote Servers Work

Each remote server runs a lightweight HTTP agent (`vpnmanager-agent`). The main server communicates with it over HTTP using an API key for authentication.

**Bootstrap flow:**
1. You provide SSH credentials for the remote server
2. The main server connects via SSH, installs the agent, and starts it as a systemd service
3. After bootstrap, SSH is no longer needed — all ongoing operations go through the agent's HTTP API

If SSH bootstrap is not suitable, follow the manual-agent instructions included
with the licensed agent package. They are versioned together; do not copy a stub
from this repository or an agent from a different release.

---

## Adding a Server via SSH Bootstrap (Recommended)

1. Go to **Servers → Add Server**
2. Fill in:
   - **Name** — a label for this server
   - **Endpoint** — public IP and WireGuard port, e.g. `203.0.113.10:51820`
   - **Interface** — WireGuard interface name, e.g. `wg0` (or `awg0` for AmneziaWG)
   - **Server Type** — `wireguard` or `amneziawg`
   - **SSH Host** — IP or hostname for SSH access
   - **SSH Port** — default 22
   - **SSH User** — usually `root`
   - **SSH Password** or **SSH Private Key**
3. Click **Save**, then click **Install Agent**

The system connects via SSH, uploads the licensed agent package, installs
dependencies into a dedicated venv at `/opt/vpnmanager-agent/`, creates a systemd
service, and verifies the agent is running.

After successful bootstrap, the server switches to **agent mode** automatically.

### Bootstrap Requirements

- The remote server must be reachable from the main server over SSH
- Root or sudo access required
- Python 3.10+ must be available on the remote server
- Port 8001 (agent) must be accessible from the main server, preferably through a
  private network or a firewall rule limited to that source

The bootstrap script checks for WireGuard or AmneziaWG tools and returns an error early if they are missing rather than proceeding with a broken installation.

---

## Server Types

### WireGuard

Standard protocol. Works with the `wg` / `wg-quick` tools. The interface is typically `wg0`.

```
Interface: wg0
Config path: /etc/wireguard/wg0.conf
```

### AmneziaWG

Obfuscated WireGuard. Requires the `amneziawg-dkms` kernel module and `awg` / `awg-quick` tools. The interface is typically `awg0`.

```
Interface: awg0
Config path: /etc/amneziawg/awg0.conf
```

When you select `amneziawg` as the server type, you can configure the obfuscation parameters (Jc, Jmin, Jmax, S1, S2, H1–H4). If you leave them blank, sensible defaults are used.

Clients connecting to an AmneziaWG server must use the **AmneziaVPN** app, not the standard WireGuard client.

---

## Discover Server

If WireGuard is already configured on a remote server (e.g. an existing installation), use **Discover** to import its configuration:

1. Go to **Servers → Discover**
2. Enter SSH credentials for the remote server
3. The system reads the existing WireGuard config, imports server keys, address pool, and existing peers

Discovered clients are imported into the database. Existing WireGuard configuration is not changed.

---

## Manual agent installation

Use the instructions bundled with the licensed agent package; they match the
package and panel versions. Generate a unique key for each remote node, restrict
network access to the control server, and never publish the key in an issue or
paste it into logs shared with support.

---

## Verify Agent Status

In the admin panel, go to **Servers** and check the status badge:

- **Online** — agent is reachable and WireGuard is running
- **Offline** — agent is not responding
- **Drifted** — DB state does not match the live WireGuard interface (see below)

You can also check manually from the main server:

```bash
curl -H "X-Api-Key: your-key" http://remote-ip:8001/health
```

Expected response:

```json
{"status": "ok", "interface": "wg0", "peers": 12}
```

On the remote server:

```bash
systemctl status vpnmanager-agent
journalctl -u vpnmanager-agent -n 50 --no-pager
```

---

## Drift Detection

Flirexa periodically compares the database state (what peers *should* be on the interface) against the live WireGuard interface (what peers *are* actually configured). This runs every 5 minutes.

**Safe drift** — a peer is in the database but missing from the live interface. This happens after a reboot or manual `wg` command. The system automatically re-adds the peer using `wg set`.

**Unsafe drift** — the WireGuard interface is down, the agent is unreachable, or there is a configuration mismatch. The server is flagged as **🟠 DRIFTED** in the Server Monitoring view.

To manually trigger reconciliation:

- Click the **🔧** button next to a drifted server in **Server Monitoring**
- Or use the API: `POST /api/v1/servers/{id}/reconcile`

---

## Multi-Server Tips

- Add servers in different geographic regions to offer location selection to clients
- Each server is independent — clients are assigned to one server per config
- The background worker monitors traffic and subscriptions across all servers
- Health monitoring runs in parallel across all servers every 60 seconds
