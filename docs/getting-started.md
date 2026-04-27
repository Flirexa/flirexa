# Getting started

Run a working VPN service in 5 minutes on a fresh Ubuntu 22.04+ / Debian 12 server.

```bash
curl -fsSL https://flirexa.biz/install.sh | sudo bash
```

That's the complete install. The script:

1. Detects your OS, picks the right packages, installs Python 3.10+, PostgreSQL, WireGuard tools, and a few system utilities.
2. Creates a `/opt/vpnmanager/` install root, a Python venv, a PostgreSQL database, and an unprivileged service user.
3. Runs Alembic migrations to create the schema.
4. Installs systemd services: `vpnmanager-api`, `vpnmanager-client-portal`, `vpnmanager-worker`, optionally `vpnmanager-admin-bot`.
5. Generates secrets (JWT signing key, encryption key for stored WireGuard private keys, internal service token) into `/opt/vpnmanager/.env`.
6. Picks safe firewall defaults (open 10086 / 10090 / your WireGuard ports).
7. Starts everything.

The admin panel is at `http://<your-server-ip>:10086` after install. The client portal is at `http://<your-server-ip>:10090`. Both run as separate FastAPI processes — admin and end-user traffic stay isolated.

> **First login**: the admin panel guides you through creating the first admin account on first visit. There's no shipped default password.

---

## What you get out of the box

After `install.sh` finishes you have **a fully working FREE-tier VPN service**:

- ✅ WireGuard + AmneziaWG protocol management
- ✅ Up to 80 clients on this single server
- ✅ Web admin panel for you
- ✅ Client portal for end users — they can self-register, pay in crypto, download configs
- ✅ Crypto payments via NOWPayments (BTC, ETH, USDT, XMR, +50 currencies)
- ✅ Admin Telegram bot (after you paste your bot token in Settings)
- ✅ Manual backup / restore
- ✅ Auto-updates pulled from GitHub Releases

You do **not** get (these need a paid license):

- ❌ Hysteria2 / TUIC — see [free vs paid](free-vs-paid.md)
- ❌ Multi-server management
- ❌ White-label branding (custom logo, colors, footer attribution removal)
- ❌ Site-to-site corporate VPN
- ❌ Promo codes, auto-renewal, scheduled backups, traffic rules
- ❌ Manager / RBAC for multi-admin access
- ❌ Full self-service Telegram client bot

When you try to create a Hysteria2 server, or add a second VPN node, or change branding, the API returns **403** with a clear explanation of which plan unlocks it.

---

## Your first 10 minutes

### 1. Log in to the admin panel

Open `http://<your-server-ip>:10086`. Create the admin account.

### 2. Add your first server

Settings → Servers → Add server. The default is your local WireGuard server, which the installer set up for you. If you have an existing remote WireGuard install you want to import, the **Discover** flow asks for SSH credentials and reads the existing config — your existing peers come along with it. *(Multi-server requires the Business+ plan.)*

### 3. Create a few clients

Clients → Add client. Name them, set traffic / bandwidth limits if you want, hit save. Download the `.conf` file or scan the QR code into the WireGuard / AmneziaWG mobile app.

That's enough for a personal VPN for you and your friends.

### 4. Enable the client portal (optional, for selling VPN)

Settings → Plans → Create plan. Set price, duration, traffic cap. The plan immediately becomes available at `http://<your-server-ip>:10090` — point your customers at that URL. They register, pay in crypto, get their config delivered automatically.

### 5. Wire up Telegram (optional)

Settings → Bots → Admin bot. Paste a bot token from `@BotFather` and your Telegram user ID. Restart the bot service. You can now manage the panel from your phone.

---

## Where to next

| If you want to … | Go to |
|---|---|
| Understand the install layout, services, file paths | [installation.md](installation.md) |
| Know what's in the open core vs paid plugins | [free-vs-paid.md](free-vs-paid.md) |
| Read the REST API reference | [api.md](api.md) |
| Understand how plugins load and how to write your own | [plugins.md](plugins.md) |
| Set up backups and disaster recovery | [backup-restore.md](backup-restore.md) |
| Configure auto-updates / change update channel | [updates.md](updates.md) |
| Debug something that broke | [troubleshooting.md](troubleshooting.md) |
| Upgrade to a paid plan | [licensing.md](licensing.md) |
