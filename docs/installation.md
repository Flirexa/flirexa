# Installation

---

## System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| OS | Ubuntu 22.04 / Debian 12 | Ubuntu 24.04 LTS |
| CPU | 1 core | 2 cores |
| RAM | 1 GB | 2 GB |
| Disk | 10 GB | 20 GB |
| Access | Root or sudo | Root or sudo |
| Network | Public IP | Public IP + domain name |

Supported distributions: Ubuntu 22.04+, Debian 12+, Linux Mint 21+, Pop!_OS 22.04+.

The installer requires internet access to download packages from apt and pip.

---

## Option A: Automated Install (Recommended)

```bash
tar xzf vpn-manager-v1.5.48.tar.gz
cd vpn-manager-v1.5.48
sudo bash install.sh
```

The installer runs fully interactive. It will ask for:

- **Telegram bot tokens** — optional, can be configured later via the admin panel
- **Admin Telegram user IDs** — who receives admin bot notifications
- **WireGuard endpoint** — auto-detected, you confirm or override (format: `ip:port`)
- **Activation code** — `XXXX-XXXX-XXXX-XXXX` format, or skip to start a 7-day trial

The installer performs these steps automatically:

1. Installs system packages: PostgreSQL, WireGuard tools, Python 3.10+
2. Creates the database and generates secure credentials
3. Creates a Python virtual environment and installs dependencies
4. Generates `.env` with unique secrets
5. Initializes the database schema via Alembic migrations
6. Installs and enables systemd services
7. Enables IP forwarding
8. Creates and starts the local WireGuard interface (`wg0`)
9. Registers the local server in the admin panel
10. Runs a post-install health check

When complete, the installer prints your access URL and admin credentials.

### Non-Interactive Mode

For automated or scripted deployments:

```bash
sudo bash install.sh --non-interactive
```

Set configuration via environment variables before running:

| Variable | Description |
|----------|-------------|
| `SB_ADMIN_TOKEN` | Telegram admin bot token |
| `SB_ADMIN_USERS` | Admin Telegram user IDs (comma-separated) |
| `SB_CLIENT_TOKEN` | Telegram client bot token |
| `SB_ENDPOINT` | WireGuard endpoint in `ip:port` format |
| `SB_DB_PASSWORD` | PostgreSQL password (auto-generated if not set) |
| `SB_ACTIVATION_CODE` | Activation code (`XXXX-XXXX-XXXX-XXXX`) |

Example:

```bash
export SB_ENDPOINT="203.0.113.10:51820"
export SB_ACTIVATION_CODE="ABCD-1234-EFGH-5678"
sudo -E bash install.sh --non-interactive
```

### Custom Install Directory

```bash
sudo bash install.sh --install-dir /opt/custom-path
```

Default install directory is `/opt/vpnmanager`.

---

## Option B: Docker

```bash
tar xzf vpn-manager-v1.5.48.tar.gz
cd vpn-manager-v1.5.48
cp .env.example .env
```

Edit `.env`. Required fields:

| Variable | How to set |
|----------|-----------|
| `DB_PASSWORD` | Any secure password |
| `SECRET_KEY` | `openssl rand -hex 32` |
| `JWT_SECRET` | `openssl rand -hex 32` |
| `SERVICE_API_TOKEN` | `openssl rand -hex 32` |
| `SERVER_ENDPOINT` | `your-ip:51820` |

Start:

```bash
docker compose up -d
```

With Telegram bots:

```bash
docker compose --profile bots up -d
```

> **Note:** Docker mode requires the WireGuard kernel module on the host. The `wg` interface is managed on the host, not inside the container.

---

## First Steps After Installation

### 1. Open the Admin Panel

```
http://YOUR_SERVER_IP:10086
```

On first visit, create your administrator account. Use a strong password (minimum 8 characters).

The **client portal** (for your end-users) is available at:

```
http://YOUR_SERVER_IP:10090
```

### 2. Activate Your License

1. Open **Settings** in the sidebar
2. Scroll to the **License** section
3. Paste your activation code or license key
4. Click **Activate**

Without a license the system runs in trial mode:

| Tier | Clients | Servers | Notes |
|------|---------|---------|-------|
| Trial | 10 | 1 | 7-day limit |
| Standard | 50 | 1 | Basic features |
| Pro | 200 | 5 | Client portal, bots |
| Enterprise | Unlimited | Unlimited | All features |

### 3. Verify WireGuard

```bash
sudo systemctl status wg-quick@wg0 --no-pager
sudo wg show
```

You should see:
- Service status: `active (running)`
- Interface `wg0` listed with a public key and listening port

The admin panel → **Servers** should show the local server with status `online`.

---

## Configuration Reference

The `.env` file at the install directory holds all settings. Most can also be changed through **Settings** in the admin panel.

### Core

| Setting | Default | Description |
|---------|---------|-------------|
| `DATABASE_URL` | (auto) | PostgreSQL connection string |
| `SECRET_KEY` | (auto) | JWT signing key |
| `API_PORT` | `10086` | Admin panel port |
| `CLIENT_PORTAL_PORT` | `10090` | Client portal port |
| `SERVER_ENDPOINT` | (auto) | WireGuard `ip:port` |
| `WORKER_ENABLED` | `true` | Run background worker as separate service |

### Telegram Bots

| Setting | Description |
|---------|-------------|
| `ADMIN_BOT_TOKEN` | Token from @BotFather |
| `ADMIN_BOT_ALLOWED_USERS` | Comma-separated Telegram user IDs |
| `CLIENT_BOT_TOKEN` | Client bot token |
| `CLIENT_BOT_ENABLED` | `true` or `false` |

### Payments

| Setting | Description |
|---------|-------------|
| `CRYPTOPAY_API_TOKEN` | CryptoPay (@CryptoBot) API token |
| `CRYPTOPAY_TESTNET` | `true` for sandbox, `false` for live |

---

## Service Management

```bash
# Check all services
systemctl status vpnmanager-api
systemctl status vpnmanager-worker
systemctl status vpnmanager-client-portal
systemctl status vpnmanager-admin-bot
systemctl status vpnmanager-client-bot

# Restart a service
systemctl restart vpnmanager-api

# View live logs
journalctl -u vpnmanager-api -f

# Last 100 lines
journalctl -u vpnmanager-api -n 100 --no-pager
```

---

## HTTPS / SSL

### During Installation

The installer can configure TLS automatically. In interactive mode it will ask you. In non-interactive mode:

```bash
export SB_WEB_SETUP_MODE=portal_admin_domain
export SB_CLIENT_PORTAL_DOMAIN=portal.example.com
export SB_ADMIN_PANEL_DOMAIN=admin.example.com
export SB_CERTBOT_EMAIL=admin@example.com
sudo -E bash install.sh --non-interactive
```

### After Installation

```bash
cd /opt/vpnmanager
sudo bash scripts/configure-web-access.sh \
  --mode portal_admin_domain \
  --portal-domain portal.example.com \
  --admin-domain admin.example.com \
  --email admin@example.com
```

Or configure via **Settings → Web Access** in the admin panel.

**Requirements:**
- DNS must already point to this server before running certbot
- Let's Encrypt requires ports 80 and 443 to be reachable from the internet

---

## Reset Admin Password

If you lose access to the admin panel:

```bash
cd /opt/vpnmanager
source venv/bin/activate
python3 main.py reset-admin --username admin --password new-secure-password
```
