# Architecture

A 10-minute tour of how Flirexa is put together.

---

## High level

```
┌──────────────────────────────────────────────────────────────────────┐
│                          Operator's server                           │
│                                                                      │
│  ┌────────────────────┐       ┌────────────────────┐                 │
│  │   admin Vue SPA    │       │  client portal Vue │                 │
│  │       :10086       │       │       :10090       │                 │
│  └─────────┬──────────┘       └──────────┬─────────┘                 │
│            │                              │                          │
│  ┌─────────▼─────────────────────┐  ┌────▼────────────────────┐      │
│  │  vpnmanager-api               │  │  vpnmanager-client-portal│     │
│  │  (FastAPI)                    │  │  (FastAPI)               │     │
│  │                               │  │                          │     │
│  │  /api/v1/clients              │  │  /client-portal/...      │     │
│  │  /api/v1/servers              │  │                          │     │
│  │  /api/v1/payments             │  │  proxies admin tasks via │     │
│  │  /api/v1/system/...           │  │  internal service token  │     │
│  │  /api/v1/plugins/...          │  │                          │     │
│  └─────────┬─────────────────────┘  └────┬─────────────────────┘     │
│            │                              │                          │
│            │  ┌──────────────────┐        │                          │
│            └──┤  PostgreSQL DB   │◄──────┘                           │
│               │  (or SQLite)     │                                   │
│               └──────────────────┘                                   │
│                                                                      │
│  ┌────────────────────────┐    ┌────────────────────────┐            │
│  │  vpnmanager-worker     │    │  vpnmanager-admin-bot  │            │
│  │  (background tasks)    │    │  (Telegram, optional)  │            │
│  └────────────────────────┘    └────────────────────────┘            │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │  WireGuard / AmneziaWG kernel interfaces (wg0, eeee, ...)    │    │
│  └──────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────┘

         (paid plans only — multi-server plugin)
                          │
                          ▼
                   ┌──────────────┐
                   │   Remote     │
                   │  VPN node    │
                   │   :80        │
                   │ (vpnmanager- │
                   │   agent)     │
                   └──────────────┘
```

Every box above is a separate process. The split keeps admin traffic and end-user traffic isolated, lets you restart one without disturbing the other, and gives clean systemd boundaries.

---

## Repository layout

```
flirexa/
├── main.py                    Admin API entry point
├── client_portal_main.py      Client portal entry point (separate FastAPI app)
├── agent.py                   Remote VPN-node agent (paid plugin: multi-server)
├── worker_main.py             Background-task entry point
│
├── src/
│   ├── api/
│   │   ├── routes/            FastAPI routers (clients, servers, payments, …)
│   │   ├── middleware/
│   │   │   ├── auth.py        JWT auth for admin and portal
│   │   │   └── license_gate.py  require_license_feature() dependency
│   │   └── main.py            App factory, startup hooks, plugin loading
│   │
│   ├── core/
│   │   ├── wireguard.py       WireGuard manager — FREE
│   │   ├── amneziawg.py       AmneziaWG manager — FREE
│   │   ├── hysteria2.py       STUB (real impl in flirexa-pro)
│   │   ├── tuic.py            STUB (real impl in flirexa-pro)
│   │   ├── proxy_base.py      STUB
│   │   ├── client_manager.py  Client lifecycle
│   │   ├── server_manager.py  Server lifecycle, including remote agents
│   │   └── traffic_manager.py Bandwidth caps, throttling
│   │
│   ├── modules/
│   │   ├── license/
│   │   │   ├── manager.py     LicenseManager — FREE / paid tier handling
│   │   │   └── online_validator.py  Heartbeat to license server (paid only)
│   │   ├── plugin_loader/
│   │   │   ├── base.py        Plugin base class + manifest validator
│   │   │   └── loader.py      Discovery + license-gated loading
│   │   ├── corporate/         STUB (real impl in flirexa-pro)
│   │   ├── payment/           Provider abstraction + factory
│   │   ├── subscription/      Subscription manager, client portal API
│   │   ├── health/            System health checker
│   │   └── ...                (see Modules section below)
│   │
│   ├── bots/
│   │   ├── admin_bot.py       Admin Telegram bot — FREE
│   │   └── client_bot.py      Client Telegram bot — paid (telegram_client_bot)
│   │
│   ├── database/
│   │   ├── models.py          SQLAlchemy ORM models
│   │   └── connection.py      Engine + session factory
│   │
│   ├── web/
│   │   ├── frontend/          Vue 3 admin SPA source
│   │   └── client-portal/     Vue 3 client portal SPA source
│   │
│   └── cli/                   `vpnmanager` CLI tool
│
├── plugins/                   Plugin shells, license-gated by manifest
│   ├── _example/              Reference scaffold for community plugins
│   ├── extra-protocols/       (skipped on FREE; loaded with proxy_protocols feature)
│   ├── multi-server/          (skipped on FREE; loaded with multi_server feature)
│   ├── corporate-vpn/
│   ├── client-tg-bot/
│   ├── traffic-rules/
│   ├── promo-codes/
│   ├── auto-backup/
│   ├── white-label-basic/
│   ├── manager-rbac/
│   └── payments/              Drop-in payment providers (Stripe, Mollie, …)
│
├── alembic/                   DB migrations
├── deploy/                    systemd unit templates
├── docs/                      You are here
├── tests/                     pytest suite
└── install.sh, update.sh, uninstall.sh
```

Implementation files for the paid plugins live in the **private** `Flirexa/flirexa-pro` repository. The public repo carries minimal stubs that preserve import paths and raise `NotImplementedError` if anything actually tries to instantiate them — which only happens on paid installs after the official installer overlays the real code.

---

## Modules

| Module | Purpose | Tier |
|---|---|---|
| `src/modules/license/` | RSA-PSS license validation, hardware binding, online heartbeat | FREE infrastructure (no-op without `LICENSE_KEY`) |
| `src/modules/plugin_loader/` | Manifest validation, license-gated plugin loading | FREE |
| `src/modules/payment/` | `PaymentProvider` interface + dispatcher | FREE (NOWPayments built-in; others as drop-in plugins) |
| `src/modules/subscription/` | Subscription lifecycle, client-portal-side API | FREE |
| `src/modules/health/` | Multi-component health checks (DB, WG interfaces, agents) | FREE |
| `src/modules/system_status/` | Aggregated status for the admin dashboard | FREE |
| `src/modules/updates/` | Auto-update orchestration via GitHub Releases | FREE |
| `src/modules/email/` | SMTP for verification mails, password resets | FREE |
| `src/modules/branding.py` | Branding values; gated mutation in white-label plugin | FREE (read) / paid (write) |
| `src/modules/business_validator.py` | Runtime invariant checks (subscription↔client, traffic limits) | FREE |
| `src/modules/failsafe.py` | Block payments / new clients in critical state | FREE |
| `src/modules/operational_mode.py` | Resolve maintenance / update / degraded modes | FREE |
| `src/modules/state_reconciler.py` | Detect WG drift between DB and live interface | FREE |
| `src/modules/backup_manager.py` | Backup / restore — manual on FREE, scheduled on `auto-backup` plugin | FREE / paid |
| `src/modules/notifications.py` | Email + Telegram notifications | FREE |
| `src/modules/corporate/` | **STUB**. Site-to-site VPN — real impl in `flirexa-pro/corporate-vpn` | paid (Enterprise) |

---

## Plugin loading at startup

```
api/main.py startup hook
   │
   ▼
1. Init DB, run pending migrations
2. Load LicenseManager
       LICENSE_KEY empty?  → FREE mode, no network calls
       LICENSE_KEY present? → validate signature, contact license server,
                              graceful fallback to FREE if signature bad
   │
   ▼
3. Init payment providers (NOWPayments, PayPal, CryptoPay) from .env
4. Load drop-in payment plugins from plugins/payments/*.py
5. Generic plugin loader scans plugins/<name>/ directories
       For each:
         a. Read + validate manifest.json
         b. Skip if name starts with _ or is in payments/
         c. Check LicenseManager.has_feature(requires_license_feature)
            ├── False → skip silently (single debug log line)
            └── True  → import __init__.py, instantiate PLUGIN, mount router
6. Restore fail-safe state from DB
7. Restore bandwidth limits (tc rules)
8. Start background workers (license heartbeat, monitoring cycles)
   │
   ▼
   Ready
```

A FREE install runs steps 1–8 with the loader scanning `plugins/` and skipping every paid one without leaving any network call or imported code behind. The install behaves exactly the same with or without paid plugin directories present — they just sit dormant.

---

## Where requests go

```
Browser → :10086/api/v1/clients
   │
   ▼
auth middleware (JWT)
   │
   ▼
operational-mode middleware (block during maintenance / update)
   │
   ▼
license middleware (URL-prefix gates: /traffic-rules, /payments, /promo-codes)
   │
   ▼
route handler (clients.py)
   │   │
   │   └── per-route Depends(require_license_feature("multi_server"))
   │       for endpoints that need a specific feature flag
   │
   ▼
ManagementCore → ClientManager → WireGuardManager
                                 (or AmneziaWGManager / Hysteria2Manager / TUICManager)
                                 │
                                 └── runs `wg`, `wg-quick` etc. via subprocess,
                                     or talks to a remote vpnmanager-agent over HTTP
```

For Hysteria2/TUIC, that last step calls into the stubs in the public repo, which raise `NotImplementedError`. On paid installs, the real implementations from `flirexa-pro` overlay these stubs and the call proceeds normally.

---

## Database

PostgreSQL is the recommended backend; SQLite is supported for development and small installs. Schema is managed by Alembic. The full schema is documented in [api.md](api.md) by way of the OpenAPI / Swagger UI at `/docs`.

Notable model conventions:

- **Encrypted columns** for WireGuard private keys and other secrets — see `src/database/encrypted_type.py`. Field-level encryption uses `VMS_ENCRYPTION_KEY` from `.env`; if it's not set, Flirexa falls back to `/etc/machine-id` (and warns loudly). **If you migrate the DB to a different host without copying `VMS_ENCRYPTION_KEY`, the encrypted columns become unreadable.**
- **`SystemConfig` key/value store** for things that don't deserve a dedicated table: feature flags, maintenance mode, fail-safe state.
- **`UpdateHistory`** records every upgrade attempt with status, log, backup pointer — used for the Updates view in the admin panel and for orphan reconciliation after an interrupted upgrade.

---

## Why open-core, not pure open or pure closed

The closed pre-1.5 product had no public users — anonymous vendor + crypto-only payments + closed source = zero discoverability. Marzban, Hiddify, 3X-UI all proved that operators in this niche pick open code. So 1.5.0 opens the parts that matter to those operators (FREE-tier core) and keeps closed only the parts that matter to **commercial operators** who want multi-server, white-label, and corporate VPN.

Concretely:

- **What's open and easy to fork:** the core product. WireGuard + AmneziaWG, panel, client portal, Telegram admin bot, auto-updates, plugin system. The MIT license means you can run it, modify it, ship it as part of your own product. We hope you build interesting things.
- **What's gated at the API layer (open code, paid feature flag):** multi-server orchestration, white-label, traffic rules, auto-backup, manager RBAC. The actual code is in this repository. The license gates fund development. Removing the gates in a fork is technically easy — but you'd be running a smaller-than-necessary fork without our updates and security fixes, against ~15 KB of feature-flag code that we'll keep extending.
- **What's genuinely closed-source:** Hysteria2, TUIC, and the corporate VPN module. The implementations live in the private `Flirexa/flirexa-pro` repository and reach paying users only through signed plugin packages from the license server. The public repo carries `NotImplementedError` stubs.

This is the same model GitLab, Sentry, PostHog, and Cal.com use. It's the model that Marzban-like ecosystems converge on once they need to fund full-time development.
