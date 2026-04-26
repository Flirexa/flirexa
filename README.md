# Flirexa

**Self-hosted VPN management panel for WireGuard, AmneziaWG, Hysteria2, and TUIC.**

Run your own VPN service — for yourself, your friends, or as a business — with a real admin panel, a client portal that takes payments, and Telegram bot integration. Open core under MIT, with optional paid plugins for multi-server, white-label, corporate VPN, and more.

```bash
# Quick install on a fresh Ubuntu/Debian server (single command):
curl -fsSL https://flirexa.com/install.sh | sudo bash
```

> Public domain (`flirexa.com`) is being migrated; until it's live, set
> `FLIREXA_DOMAIN` and `LICENSE_SERVER_URL` env vars to your own server.

---

## What you get for free

The open core ships with a fully working VPN service for a single operator:

- **WireGuard + AmneziaWG** server management (DPI-resistant — works in censorship-heavy networks).
- **Up to 80 clients on 1 server** — no online license check, no expiry, no kill switch.
- **Web admin panel** (Vue 3) with real-time client/server stats, traffic graphs, QR codes.
- **Admin Telegram bot** for managing the service from your phone.
- **Client portal** (separate process on port 10090) where end-users self-register, pick a plan, pay, and download configs.
- **NOWPayments** (crypto) integration out of the box.
- **6 languages**: English, Russian, Ukrainian, German, French, Spanish.
- **Auto-updates** via GitHub Releases (no phone-home).
- **Manual backup/restore** with full data export.
- **6 payment-provider plugins** in `plugins/payments/` (Stripe, Mollie, Razorpay, Payme, CryptoPay, NOWPayments) — drop one in, restart, configured via `.env`.

If you can run a VPS, you can run a VPN service.

## What's paid

The paid plugins live in `plugins/<name>/` as license-gated declarations. Without a valid license the plugin loader skips them and the corresponding API endpoints return **403** with a clear upgrade hint. With a license they activate automatically.

| Tier | Plugin | What unlocks |
|---|---|---|
| **Starter** ($19/mo) | `extra-protocols` | Hysteria2 + TUIC proxy protocols |
| Starter | `promo-codes` | Promo codes, auto-renewal, basic referrals |
| **Business** ($49/mo) | `multi-server` | Manage multiple servers from one panel |
| Business | `client-tg-bot` | Full self-service Telegram bot for end users |
| Business | `traffic-rules` | Per-client and global throttling rules |
| Business | `white-label-basic` | Custom logo, colors, footer attribution removal |
| Business | `auto-backup` | Scheduled backups + remote storage mounts |
| **Enterprise** ($149/mo) | `corporate-vpn` | Site-to-site mesh VPN for branch offices |
| Enterprise | `manager-rbac` | Multi-admin roles with permission scopes |

Pricing and licenses: see [flirexa.com/pricing](https://flirexa.com/pricing) (when available).

## Why this exists

The self-hosted VPN management space has good free tools (Marzban, Hiddify, 3X-UI) and good closed tools — but very little in between. Flirexa is open-core: a genuinely useful free product that small operators can grow with, plus paid plugins for serious commercial operators who need multi-server orchestration, white-label, and B2B features.

If you fork, run, and never pay a cent, that's fine — that's the deal. If your service grows past what FREE can do, the upgrade path is clear.

## Architecture

- **`main.py`** — FastAPI admin API + Vue 3 SPA on port 10086.
- **`client_portal_main.py`** — separate FastAPI process for the client-facing portal on port 10090.
- **`agent.py`** — lightweight HTTP agent installed on remote VPN nodes (paid plugin: `multi-server`).
- **`src/core/`** — protocol managers (WireGuard, AmneziaWG, Hysteria2, TUIC), client/server lifecycle, traffic monitoring.
- **`src/modules/license/`** — license validation. Empty `LICENSE_KEY` → FREE mode, no network calls.
- **`src/modules/plugin_loader/`** — generic loader that scans `plugins/`, validates manifests, mounts routers based on license entitlement.
- **`plugins/`** — per-feature plugin directories. Each has a `manifest.json` declaring which license feature it requires.

More: [`docs/architecture.md`](docs/architecture.md), [`AGENT_ARCHITECTURE.md`](AGENT_ARCHITECTURE.md).

## Installation

### Quick install (Ubuntu 22.04+ / Debian 12+)

```bash
curl -fsSL https://flirexa.com/install.sh | sudo bash
```

### From source

```bash
git clone https://github.com/Flirexa/flirexa.git
cd flirexa
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # edit as needed
alembic upgrade head
python main.py
```

The admin panel is at `http://<your-server-ip>:10086`. First login creates the admin account.

## Configuration

Everything is `.env`. Key vars:

```ini
# License (leave empty for FREE mode)
LICENSE_KEY=

# License server (required for paid tiers, ignored on FREE)
LICENSE_SERVER_URL=https://flirexa.com

# Telegram (optional — admin bot)
ADMIN_BOT_TOKEN=

# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/flirexa
# or
DATABASE_URL=sqlite:///data/flirexa.db
```

See `.env.example` for the full reference.

## Plugins

The plugin system in `src/modules/plugin_loader/` is open and documented. To write a community plugin:

1. Copy `plugins/_example/` to `plugins/<your-plugin-name>/`.
2. Edit `manifest.json` (kebab-case `name`, semver `version`, list `requires_license_feature` if it should be license-gated).
3. Implement your plugin in `__init__.py` — export a `PLUGIN` instance subclassing `src.modules.plugin_loader.Plugin`.
4. Restart the API.

Community plugins that don't need license gating are welcome — set `requires_license_feature` to a flag your installs always have, or open an issue and we'll add a `community` flag that's always granted.

## Contributing

PRs and issues welcome. See [`CONTRIBUTING.md`](CONTRIBUTING.md) and [`SECURITY.md`](SECURITY.md).

## License

MIT — see [`LICENSE`](LICENSE).
