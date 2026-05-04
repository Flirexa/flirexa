# Installation

## Supported Deployment Model

VPN Management Studio is sold as a **single-node self-hosted control plane**.

Officially supported production profile:

| Component | Supported | Notes |
|---|---|---|
| OS | Ubuntu Server 24.04 LTS, Ubuntu Server 22.04 LTS | Production support matrix |
| Database | Local PostgreSQL 15/16 | Installed and managed on the same node |
| Topology | Single-node control plane | No HA / multi-node control plane support |
| Privileges | `root` required | Install, update, restore, rollback |
| CPU | 2 vCPU minimum | 4 vCPU recommended |
| RAM | 4 GB minimum | 8 GB recommended |
| Disk | 40 GB minimum | 80 GB recommended |

Required inbound ports depend on enabled features:
- `22/tcp` — SSH
- `80/tcp` — ACME / HTTP redirect
- `443/tcp` — admin/client HTTPS when web access is enabled
- `10086/tcp` — API/admin panel in direct mode
- `10090/tcp` — client portal in direct mode
- `51820/udp` — WireGuard default
- proxy ports if enabled, for example `8443/udp`

## What The Installer Guarantees

A successful `install.sh` run guarantees:
- install root is created
- runtime layout exists: `releases/`, `staging/`, `backups/`, `update-lock/`, `current`
- Python virtual environment is created
- `.env` is generated or reused
- PostgreSQL is initialized and reachable
- database schema is initialized and stamped at current Alembic head
- systemd units are installed and enabled as applicable
- `vpnmanager` CLI is installed into `/usr/local/bin/vpnmanager`
- API health check passes
- client portal service is installed when web components are enabled

The installer does **not** guarantee:
- remote agents are deployed
- SSL certificates are always issued successfully on the first try
- admin user is created automatically

The first admin account is created on first visit to the admin panel.

## Default Paths

Default install root:
- `/opt/vpnmanager`

Key paths after install:

| Path | Purpose |
|---|---|
| `/opt/vpnmanager/.env` | product environment file |
| `/opt/vpnmanager/current` | active runtime pointer |
| `/opt/vpnmanager/releases/` | versioned releases |
| `/opt/vpnmanager/staging/` | update staging |
| `/opt/vpnmanager/backups/` | product backups |
| `/opt/vpnmanager/backups/update_backups/` | update/rollback backups |
| `/usr/local/bin/vpnmanager` | official operational CLI |

## Installation

Interactive install:

```bash
tar xzf vpn-manager-v<version>.tar.gz
cd vpn-manager-v<version>
sudo bash install.sh
```

Non-interactive install:

```bash
sudo bash install.sh --non-interactive
```

Useful environment variables:

| Variable | Purpose |
|---|---|
| `SB_ACTIVATION_CODE` | activate commercial license during install |
| `SB_ENDPOINT` | explicit VPN endpoint `ip:port` |
| `SB_CLIENT_PORTAL_DOMAIN` | portal domain |
| `SB_ADMIN_PANEL_DOMAIN` | admin domain |
| `SB_CERTBOT_EMAIL` | email for TLS |
| `SB_WEB_SETUP_MODE` | web access mode |

## First Commands After Installation

Run these first:

```bash
sudo vpnmanager status
sudo vpnmanager health
sudo vpnmanager services status
sudo vpnmanager license status
```

Expected healthy result on a new server:
- `vpnmanager status` -> `SUCCESS`
- `vpnmanager health` -> `SUCCESS` or temporarily `DEGRADED` during very early startup windows

## Service Management

Official product interface is the CLI:

```bash
sudo vpnmanager services status
sudo vpnmanager services restart --api
sudo vpnmanager services restart --all --yes
```

For low-level troubleshooting:

```bash
systemctl status vpnmanager-api
journalctl -u vpnmanager-api -n 100 --no-pager
```
