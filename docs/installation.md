# Installation reference

The full picture of what `install.sh` does, where things go, and how to do non-default installs.

For "I just want this to work", see [getting-started.md](getting-started.md) — it's a one-liner.

---

## Supported targets

| OS | Status |
|---|---|
| Ubuntu 22.04 LTS | ✅ Tier-1 |
| Ubuntu 24.04 LTS | ✅ Tier-1 |
| Debian 12 | ✅ Tier-1 |
| Debian 11 | ⚠️ Works, EOL approaching |
| AlmaLinux 9 / RHEL 9 | ⚠️ Works with `dnf` package mapping; less tested |
| Other Linux | DIY — see "From source" below |

Both ARM64 and AMD64 are supported.

> **Container note:** Flirexa needs `wireguard` kernel module + `setcap CAP_NET_ADMIN`. Running inside a container works only if the host kernel has WireGuard and the container can talk to host networking. Bare-metal or VPS is the recommended target.

---

## One-liner install (recommended)

```bash
curl -fsSL https://flirexa.biz/install.sh | sudo bash
```

Re-running the same command after changes safely upgrades in place — the script detects an existing install at `/opt/vpnmanager/` and runs the update path.

### Available env vars (non-interactive)

```bash
SB_DB_PASSWORD=mypassword            \
SB_ADMIN_TOKEN=123:abc-bot-token     \
SB_ADMIN_USERS=1234567890,987654321  \
SB_ENDPOINT=1.2.3.4:51820            \
SB_WEB_SETUP_MODE=portal_admin_ip    \
curl -fsSL https://flirexa.biz/install.sh | sudo bash -s -- --non-interactive
```

Pass `--help` for the full list:

```bash
curl -fsSL https://flirexa.biz/install.sh | sudo bash -s -- --help
```

---

## What gets installed where

```
/opt/vpnmanager/            ← install root
├── current/                ← symlink to active release directory
│   ├── main.py             ← admin API entry point
│   ├── client_portal_main.py
│   ├── agent.py            ← VPN node agent (paid: multi-server)
│   ├── src/
│   ├── plugins/
│   ├── alembic/
│   └── deploy/             ← systemd templates
├── releases/               ← versioned releases (one per upgrade)
│   ├── 1.5.0/
│   └── 1.5.1/
├── venv/                   ← Python virtualenv
├── data/
│   └── flirexa.db          ← SQLite (if PostgreSQL unavailable)
├── backups/                ← automatic backups before upgrades
├── staging/                ← partial-download buffer for updates
└── .env                    ← all secrets and config; never in git

/etc/systemd/system/
├── vpnmanager-api.service
├── vpnmanager-client-portal.service
├── vpnmanager-worker.service
├── vpnmanager-admin-bot.service       ← started after you paste a token
└── vpnmanager-client-bot.service      ← only with paid client-tg-bot plugin

/etc/wireguard/             ← WireGuard configs (managed by Flirexa, don't edit by hand)
├── wg0.conf                ← FREE installs only have wg0
└── wg-local-1.conf
```

The PostgreSQL data is in the system default location (`/var/lib/postgresql/<version>/main/` on Ubuntu). Flirexa creates a database `vpnmanager_db` and a role `vpnmanager` with a randomly-generated password stored in `/opt/vpnmanager/.env`.

---

## Ports

| Port | Service | Public? |
|---|---|---|
| **10086** | Admin API + Vue SPA | usually behind a reverse proxy with TLS |
| **10090** | Client portal | exposed to your end users with TLS |
| **51820** | WireGuard (default) | exposed to the internet |
| **80** | Optional VPN-node agent on remote servers (paid) | exposed; agents authenticate via shared key |

Standard pattern: front the admin and client-portal ports with nginx + Let's Encrypt. The installer offers to do this for you when you pass `SB_WEB_SETUP_MODE=portal_admin_domain` plus the relevant domain env vars.

---

## From source (for developers and unusual platforms)

```bash
git clone https://github.com/Flirexa/flirexa.git
cd flirexa
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Set up DB
cp .env.example .env
# edit .env — at minimum set DATABASE_URL and JWT_SECRET
alembic upgrade head

# Run
python main.py                                 # admin API on 10086
python client_portal_main.py                   # client portal on 10090
python -m src.bots.admin_bot                   # admin Telegram bot (optional)
```

For development we recommend the dev `docker-compose` — see [CONTRIBUTING.md](../CONTRIBUTING.md#development-environment).

---

## Docker Compose

```bash
git clone https://github.com/Flirexa/flirexa.git
cd flirexa
docker compose up -d
```

The bundled `docker-compose.yml` brings up Flirexa + PostgreSQL on a single host. It's intentionally simple — production deployments should use systemd via `install.sh`.

---

## Upgrading

### From within the panel

Settings → Updates → Check for updates → Apply. The admin panel handles the whole flow: download from GitHub Releases, verify SHA-256, take a backup, run Alembic migrations, restart services, smoke-check.

### From the command line

```bash
sudo bash /opt/vpnmanager/current/update.sh
```

Same flow as the panel, useful for cron / unattended upgrades.

### Manual

If something goes sideways and you want to install a specific version by hand:

```bash
sudo systemctl stop vpnmanager-api vpnmanager-client-portal vpnmanager-worker
cd /opt/vpnmanager/releases
sudo tar xzf /path/to/flirexa-1.5.0.tar.gz
sudo ln -snf /opt/vpnmanager/releases/1.5.0 /opt/vpnmanager/current
sudo /opt/vpnmanager/venv/bin/alembic -c /opt/vpnmanager/current/alembic.ini upgrade head
sudo systemctl start vpnmanager-api vpnmanager-client-portal vpnmanager-worker
```

`backup-restore.md` covers the rollback flow if you need to undo an upgrade.

---

## Uninstalling

```bash
curl -fsSL https://flirexa.biz/uninstall.sh | sudo bash
```

The uninstaller stops services, removes systemd units, the install directory, the database, the firewall rules. It does **not** touch other things on the server (PostgreSQL itself, your nginx config, your TLS certs).

> **Backup first.** The uninstaller is non-recoverable. If you might want your data later, run a manual backup from the panel before uninstalling.

---

## Troubleshooting install issues

If something breaks during install:

1. The script writes a full log to `/var/log/vpnmanager-install.log`. Read the last 100 lines.
2. Re-run with `bash -x` for shell-level tracing: `sudo bash -x install.sh`.
3. Common gotchas in [troubleshooting.md](troubleshooting.md).
4. Open an issue at <https://github.com/Flirexa/flirexa/issues> with the log attached (redact passwords).
