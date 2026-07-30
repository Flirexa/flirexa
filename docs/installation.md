# Installation

_Last verified: 2026-07-30._

---

## System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| OS | Ubuntu Server 22.04 LTS | Ubuntu Server 24.04 LTS |
| CPU | 2 cores | 4 cores |
| RAM | 4 GB | 8 GB |
| Disk | 40 GB | 80 GB |
| Access | root | root |
| Network | Public IP | Public IP + domain name |

Other Debian-family systems may pass best-effort checks, but they are outside
the production support matrix.

The installer requires internet access to download system/Python packages and the
official Flirexa release manifest/package.

---

## Option A: Automated Install (Recommended)

```bash
curl -fsSL https://flirexa.biz/install.sh | sudo bash
```

Or clone the repository and run the installer from source:

```bash
git clone https://github.com/Flirexa/flirexa.git
cd flirexa
sudo bash install.sh
```

The installer runs fully interactive. It will ask for:

- **Telegram bot tokens** — optional, can be configured later via the admin panel
- **Admin Telegram user IDs** — who receives admin bot notifications
- **WireGuard endpoint** — auto-detected, you confirm or override (format: `ip:port`)
- **Activation code** — or `N` to run the FREE tier (80 clients, no expiry)
- **Optional HTTPS setup** — domains and a Let's Encrypt contact email when selected

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

On an in-place reinstall, all managed services including the background worker
are stopped before application files are replaced. Package-owned compiled admin
and portal output directories are pruned before new hashed assets are copied;
database contents, `.env`, uploads, licence state, and backups are preserved.

When complete, the installer prints the access URL. The first browser visit creates
the administrator account.

### Installer diagnostics

By default, the installer sends coarse phase events to the official Flirexa service.
A failed event can include a bounded tail of the install log; the receiving web
server also sees the request source IP as it does for any HTTP request. Client
records, VPN keys, database contents, bot tokens, and generated secrets are not
part of this event payload.

The interactive installer also offers optional installation assistance. If the
operator enters an email address, that is explicit consent for Flirexa to send
one English-language help email only if this installation attempt fails. The
address is not used for marketing, is deleted after a successful install, and
otherwise expires after seven days. Failure emails contain the failed stage and
installation ID, never the diagnostic log.

Disable diagnostics and the optional assistance flow before invoking the script:

```bash
curl -fsSL https://flirexa.biz/install.sh -o /tmp/flirexa-install.sh
sudo INSTALL_TELEMETRY=off bash /tmp/flirexa-install.sh
```

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
| `SB_SUPPORT_EMAIL` | Opt in to one English help email if installation fails |
| `INSTALL_TELEMETRY` | Set to `off` to disable diagnostics and optional installation assistance |

Example:

```bash
export SB_ENDPOINT="203.0.113.10:51820"
export SB_ACTIVATION_CODE="ABCD-1234-EFGH-5678"
export SB_SUPPORT_EMAIL="operator@example.com"
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
git clone https://github.com/Flirexa/flirexa.git
cd flirexa
cp .env.example .env
```

Edit `.env`. Required fields:

| Variable | How to set |
|----------|-----------|
| `DB_PASSWORD` | Any secure password |
| `SECRET_KEY` | `openssl rand -hex 32` |
| `JWT_SECRET` | `openssl rand -hex 32` |
| `SERVICE_API_TOKEN` | `openssl rand -hex 32` |
| `VMS_ENCRYPTION_KEY` | `openssl rand -hex 32` (back this up with the database) |
| `SERVER_ENDPOINT` | `your-ip:51820` |

Start:

```bash
docker compose up -d
```

With Telegram bots:

```bash
docker compose --profile bots up -d
```

The compose stack refuses to start while example secrets remain in `.env`, and only
the API container runs Alembic migrations.

> **Docker scope:** the compose file is suitable for evaluation and control-plane
> development. A VPN data-plane deployment still requires the WireGuard kernel
> module, host networking/routing, and access to `/etc/wireguard`. The systemd
> installer is the recommended production path.

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

Without a licence key the runtime stays on the **FREE** tier — forever, with no
licence heartbeat. Installer diagnostics and update checks are separate:

| Tier | Price | Clients | Servers | Notes |
|------|-------|---------|---------|-------|
| FREE | $0 | 80 | 1 host / 2 local endpoints | WireGuard + AmneziaWG, no licence needed |
| Starter | from $12/mo | 500 | 1 host | + Hysteria2, TUIC, VLESS-Reality, promo codes |
| Business | from $49/mo | 2000 | up to 10 nodes | + multi-server, client Telegram bot, full payment suite, traffic rules, scheduled backups |
| Enterprise | from $149/mo | Unlimited | Unlimited | + corporate VPN, full white-label, standard client apps, manager RBAC |

Current checkout pricing and billing periods are listed on
[flirexa.biz](https://flirexa.biz).

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

NOWPayments is the built-in crypto provider available on FREE. Other providers are
licence-gated; their delivery/configuration differs by provider.

| Setting | Description |
|---------|-------------|
| `NOWPAYMENTS_API_KEY` | NOWPayments API key (crypto — built-in FREE provider) |
| `NOWPAYMENTS_IPN_SECRET` | NOWPayments IPN secret for webhook signature verification |
| `NOWPAYMENTS_SANDBOX` | `true` for sandbox, `false` for live |
| `CRYPTOPAY_API_TOKEN` | CryptoPay (@CryptoBot) API token |
| `CRYPTOPAY_TESTNET` | `true` for sandbox, `false` for live |
| `PAYLIO_API_KEY` | PayLio API key (paid provider) |
| `PAYLIO_PAYOUT_ADDRESS` | Polygon USDC payout address |
| `PAYLIO_CURRENCIES` | Comma-separated customer currencies (default `USD,EUR`) |

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

If you still have a working session, change your password from **Settings → Account**
in the admin panel.

If you are locked out, there is no dedicated CLI reset command. Recover access by
re-running the installer over the existing installation — it detects the existing
`.env` and lets you re-create the administrator account without touching your data:

```bash
sudo bash install.sh
```
