# Flirexa

**Self-hosted VPN management for WireGuard, AmneziaWG, Hysteria2, TUIC, and VLESS-Reality.**
Open core under MIT. Paid plugins for the parts that turn it into a real business.

_Repository and product claims last verified: 2026-07-30. Current checkout
pricing on [flirexa.biz](https://flirexa.biz) is authoritative._

[![Tests](https://github.com/Flirexa/flirexa/actions/workflows/test.yml/badge.svg)](https://github.com/Flirexa/flirexa/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Version](https://img.shields.io/github/v/release/Flirexa/flirexa?label=version&color=blue)](https://github.com/Flirexa/flirexa/releases)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![Stars](https://img.shields.io/github/stars/Flirexa/flirexa?style=social)](https://github.com/Flirexa/flirexa/stargazers)

```bash
# One command on a supported Ubuntu Server 22.04/24.04 x86-64 host:
curl -fsSL https://flirexa.biz/install.sh | sudo bash
```

![Admin dashboard](docs/screenshots/dashboard.png)

---

## Run a real VPN service. Today.

Flirexa is what you'd build if you took Marzban, gave it a working client portal, and made the multi-server / corporate / white-label parts a paid upgrade instead of unfinished issues.

**For yourself or a few friends?** Run the FREE tier and never look at this README again.
**Selling VPN as a service?** Free tier handles up to 80 clients on one physical host with crypto payments out of the box. When you outgrow it, you upgrade — the same installation, more features unlocked.

The FREE runtime has no licence heartbeat and no remote kill switch. The installer and updater do contact official Flirexa services: the updater fetches a signed manifest, while the installer reports coarse phase/failure diagnostics by default so broken installs can be supported. The installer may also ask for an optional email address; entering one opts in to a single English help email only if that attempt fails. Set `INSTALL_TELEMETRY=off` to disable installer diagnostics and the optional help flow.

---

## What you get for free

| | |
|---|---|
| **Protocols** | WireGuard + AmneziaWG (DPI-resistant — works in censorship-heavy networks) |
| **Capacity** | Up to 80 clients on one physical host, with one local WireGuard and one local AmneziaWG endpoint |
| **Admin panel** | Vue 3 SPA on port 10086 — real-time stats, traffic graphs, QR codes |
| **Client portal** | Separate FastAPI process on port 10090 — self-service signup, plans, config download |
| **Telegram** | Admin bot for managing the service from your phone |
| **Payments** | NOWPayments (BTC, ETH, USDT, XMR, +50 cryptocurrencies) out of the box |
| **Languages** | English, Русский, Deutsch, Français, Español |
| **Updates** | Signed update manifest, package checksum verification, and rollback |
| **Backup** | Manual export/restore with full data |
| **Payment providers** | NOWPayments ships in FREE. CryptoPay, PayLio, and additional card/local rails are license-gated; see [payment setup](docs/payment-setup.md) for what is included and how each provider is delivered. |

If you can run a VPS, you can run a VPN service.

---

## Screenshots

<table>
<tr>
<td width="50%">

**Admin dashboard**
![Dashboard](docs/screenshots/dashboard.png)

</td>
<td width="50%">

**Client management**
![Clients](docs/screenshots/clients.png)

</td>
</tr>
<tr>
<td width="50%">

**Multi-server view**
![Servers](docs/screenshots/servers.png)

</td>
<td width="50%">

**Client portal**
![Client portal](docs/screenshots/portal.png)

</td>
</tr>
<tr>
<td width="50%">

**Telegram bots**
![Bots](docs/screenshots/bots.png)

</td>
<td width="50%">

**Settings & branding**
![Settings](docs/screenshots/settings.png)

</td>
</tr>
</table>

---

## What's paid

Paid capabilities use signed feature flags and backend checks. The public tree
contains the MIT open core and deterministic compatibility stubs; official
customer archives supply protected commercial implementations under a separate
licence.

| Tier | Per month | Plugins unlocked |
|---|---|---|
| **Starter** | $12 | `extra-protocols` (Hysteria2, TUIC, VLESS-Reality), `promo-codes` |
| **Business** | $49 | + `multi-server`, `client-tg-bot`, full payment-provider suite, `traffic-rules`, `auto-backup` |
| **Enterprise** | $149 | + full white-label/appearance controls, standard client-app package, `corporate-vpn`, `manager-rbac` |

Automatic renewal of an operator's end-customer subscriptions is temporarily
unavailable while it is rebuilt around one verified provider settlement per
extension. Manual portal checkout and renewal continue to work. This is
separate from purchasing a monthly, annual, or Lifetime Flirexa licence.
The table applies to newly issued licences; an older key keeps any capability
that is explicitly present in its signed feature set.

**Subscriptions can be paid by card or crypto.** Card/fiat — Visa/Mastercard, Apple Pay, Google Pay, bank transfer in USD/EUR via [PayLio](https://paylio.org) recurring subscriptions; or pay in cryptocurrency via NOWPayments. If you need an invoice for accounting purposes, email `support@flirexa.biz` and we'll issue one.

Pricing and licensing: [flirexa.biz](https://flirexa.biz)

> **Why open-core?** The self-hosted VPN management space has good free tools (Marzban, Hiddify, 3X-UI) and good closed tools — but very little in between. Flirexa is what we wished existed: a genuinely useful free product that small operators can grow with, plus paid plugins for serious commercial operators who need multi-server, white-label, and B2B features.

---

## Compared to alternatives

Competitor feature sets change too quickly for a static matrix to remain honest.
Compare current releases in their official repositories:
[Marzban](https://github.com/Gozargah/Marzban),
[Hiddify](https://github.com/hiddify/hiddify-app),
[WG-Easy](https://github.com/wg-easy/wg-easy), and
[3X-UI](https://github.com/MHSanaei/3x-ui).

Flirexa's deliberate trade-off is a useful MIT-licensed FREE service for one
operator/host, with commercial protocol, orchestration, white-label, and B2B
features layered on top.

---

## Install

### Quick install (Ubuntu Server 22.04 or 24.04, Linux x86-64)

```bash
curl -fsSL https://flirexa.biz/install.sh | sudo bash
```

The installer sets up Python venv, PostgreSQL, systemd services, generates secrets, and runs the first migrations. Admin panel is at `http://<your-server-ip>:10086` afterwards. First login creates the admin account.

### From source

```bash
git clone https://github.com/Flirexa/flirexa.git
cd flirexa
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.lock
cp .env.example .env  # edit as needed
alembic upgrade head
python main.py
```

### Docker

```bash
git clone https://github.com/Flirexa/flirexa.git
cd flirexa
docker compose up -d
```

See [docs/installation.md](docs/installation.md) for details, alternative database setups, and TLS / domain config.

---

## API

The admin API is a documented FastAPI app. After install:

- **Swagger UI:** `http://<your-server-ip>:10086/api/docs`
- **OpenAPI schema:** `http://<your-server-ip>:10086/api/openapi.json`
- **Architecture overview:** [docs/architecture.md](docs/architecture.md)
- **API reference:** [docs/api.md](docs/api.md)

REST endpoints are grouped by domain (`/api/v1/clients`, `/api/v1/servers`, `/api/v1/payments`, …). Admin authentication uses a Bearer JWT. Browser client-portal sessions use short-lived HttpOnly access cookies, rotating hash-only refresh families, and CSRF protection; released mobile clients retain their compatible Bearer contract.

---

## Plugins

The plugin system is open and documented. To write a community plugin:

1. Copy `plugins/_example/` to `plugins/<your-plugin-name>/`.
2. Edit `manifest.json` (kebab-case `name`, semver `version`).
3. Set `requires_license_feature` to a feature flag your installs always have. For community plugins (no license gate), use `community` — the plugin loader treats it as universally granted.
4. Implement your plugin in `__init__.py` — export a `PLUGIN` instance subclassing `src.modules.plugin_loader.Plugin`.
5. Restart the API.

See [docs/plugins.md](docs/plugins.md) for the full plugin authoring guide and [plugins/_example/](plugins/_example/) for a working scaffold.

---

## Client apps

Android, Windows, and Linux client apps are available to Enterprise customers. They connect end users to an operator's Flirexa installation; iOS remains planned. Current availability and licensing are listed at [flirexa.biz](https://flirexa.biz).

---

## Documentation

| Topic | Where |
|---|---|
| Getting started | [docs/getting-started.md](docs/getting-started.md) |
| Installation (full reference) | [docs/installation.md](docs/installation.md) |
| Architecture overview | [docs/architecture.md](docs/architecture.md) |
| API reference | [docs/api.md](docs/api.md) |
| Plugin authoring | [docs/plugins.md](docs/plugins.md) |
| FREE vs paid (what's gated, what's not) | [docs/free-vs-paid.md](docs/free-vs-paid.md) |
| Licensing model | [docs/licensing.md](docs/licensing.md) |
| Updates & rollback | [docs/updates.md](docs/updates.md) |
| Backup & disaster recovery | [docs/backup-restore.md](docs/backup-restore.md) |
| Troubleshooting | [docs/troubleshooting.md](docs/troubleshooting.md) |
| Roadmap | [ROADMAP.md](ROADMAP.md) |
| Changelog | [CHANGELOG.md](CHANGELOG.md) |

---

## Roadmap

Active items, in rough order. See [ROADMAP.md](ROADMAP.md) for the full picture.

- **2026 Q3** — Signed distribution for separately delivered commercial extensions
- **2026 Q3** — Settlement-backed end-customer subscription renewal
- **2026 Q3** — Plugin marketplace (community-authored plugins)
- **2026 Q3** — Documentation site and additional community plugin examples
- **2026 Q4** — iOS client app and localisation expansion

The public interactive demo and Android, Windows, and Linux client apps are already available from [flirexa.biz](https://flirexa.biz).

---

## Support the project

If Flirexa saves you time or money, consider:

- ⭐ **Starring this repository** — costs nothing, helps massively with visibility.
- 💬 **Telling us what worked / what didn't** — open an issue or [discussion](https://github.com/Flirexa/flirexa/discussions).
- 💛 **Supporting development** — FREE and trial installations expose an
  optional support action in the current admin header. Purchased tiers do not
  show donation prompts or controls.

For commercial support (priority response, custom integrations, training): `support@flirexa.biz`.

---

## Contributing

PRs and issues welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md) first — they explain what we accept, what we don't, and how to set up a dev environment.

For commercial enquiries (pricing, support contracts, white-label OEM): `support@flirexa.biz`.

---

## License

MIT — see [LICENSE](LICENSE).

The contents of this repository are MIT-licensed. Separately delivered commercial extensions are covered by their own licence terms. See [docs/licensing.md](docs/licensing.md) for the full breakdown.
