# FREE vs paid

_Last verified: 2026-07-27. Current checkout pricing on [flirexa.biz](https://flirexa.biz) is authoritative._

Honest, unhedged answer to "what do I get for free and what do I have to pay for?"

If you're choosing between Flirexa and an alternative, this page is the comparison ammunition. If you're already running Flirexa and wondering whether to upgrade, this page tells you what unlocks at each tier.

---

## TL;DR

**FREE** is a complete VPN service for one operator on one physical host with up to 80 clients. WireGuard + AmneziaWG, panel, client portal, crypto payments via NOWPayments, Telegram admin bot, manual backups. MIT-licensed, install once, run forever — no payment, no expiry.

**Starter (from $12/mo)** adds Hysteria2/TUIC/VLESS-Reality protocols, promo codes, and auto-renewal.

**Business (from $49/mo)** adds multi-server, white-label, traffic rules, scheduled backups, full client Telegram bot.

**Enterprise (from $149/mo)** adds site-to-site corporate VPN, full white-label (custom domain, custom email sender), and multi-admin RBAC.

---

## What's in FREE forever

| | |
|---|---|
| **Protocols** | WireGuard, AmneziaWG |
| **Clients** | up to 80 |
| **Servers** | one physical host, up to 2 local endpoints (one WireGuard + one AmneziaWG) |
| **Admin panel** | full Vue 3 SPA on port 10086 |
| **Client portal** | full Vue 3 SPA on port 10090 with self-service signup, plans, payment, config download |
| **Telegram admin bot** | full functionality |
| **Telegram client bot** | not available (Business+ feature) |
| **Crypto payments** | NOWPayments built-in (BTC, ETH, USDT, XMR, +50 more) |
| **Other payment providers** | not in FREE — CryptoPay, PayLio, and additional card/local rails require a paid licence |
| **Languages** | EN, RU, DE, FR, ES |
| **Manual backup / restore** | yes |
| **Scheduled backups** | not available (Business+ feature) |
| **Auto-updates** | yes, from the signed official update manifest |
| **Licence heartbeat** | none — FREE runtime licences never expire and cannot be remotely disabled |
| **Source code** | the public open core is MIT-licensed; explicitly documented commercial extensions are separate |

### Limits in numbers

- **80 clients per install**: enforced by the API, not just a soft suggestion. If you hit 80, you cannot add a 81st without upgrading or deleting an existing one.
- **Up to 2 local endpoints**: one per protocol type — a single WireGuard endpoint and a single AmneziaWG endpoint on the install host. Remote nodes or another endpoint of the same protocol need the multi-server feature.
- **WireGuard endpoint count**: a single WireGuard interface can host all 80 clients comfortably.

---

## Starter — from $12 / month

For solo operators who started monetizing and outgrew the FREE protocol set or want acquisition tools.

**Adds:**

- **Hysteria2** support — QUIC-based proxy, censorship-resistant
- **TUIC** support — alternative QUIC proxy, useful when Hysteria2 is fingerprinted
- **VLESS-Reality** support — Xray-based HTTPS camouflage
- **Promo codes** — percent-off, free-day extensions, tier-restricted, expiring
- **Auto-renewal** — reminder emails N days before expiry, optional auto-charge
- **Up to 500 clients** (vs 80 on FREE)

Runs the enabled protocols on the install host. Remote-node orchestration starts at Business.

---

## Business — from $49 / month

The headline-feature tier. This is what serious commercial operators actually pay for.

**Adds:**

- **Multi-server orchestration** — manage up to 10 servers from one panel. Push clients to specific servers, balance load, see per-server traffic. Remote VPN nodes run a tiny `vpnmanager-agent` HTTP service.
- **Full client Telegram bot** — end users can register, browse plans, pay in crypto, download configs, all via Telegram. Many operators in censorship-heavy and crypto-native markets prefer this over the web portal.
- **Traffic rules** — per-client and global throttling, automatic enforcement when a quota threshold is hit
- **White-label (basic)** — replace the Flirexa logo, change brand colors, remove the "Powered by Flirexa" footer attribution
- **Scheduled backups** — daily automatic backups; mount remote storage (S3, FTP, NFS, SMB); retain N revisions
- **Up to 2,000 clients** across up to 10 servers

---

## Enterprise — from $149 / month

For ISPs, MSPs, and companies who don't run an end-user VPN service but need site-to-site connectivity.

**Adds:**

- **Corporate VPN (site-to-site)** — multi-site WireGuard mesh with subnet allocation, full-mesh routing, per-site config generation, network diagnostics. The use case is "branch-office connectivity": three offices in different cities, all employees on a private VPN, traffic routed peer-to-peer through Flirexa-managed config.
- **Full white-label** — custom domain on the client portal, custom `From` address on outbound emails, custom favicon and browser tab title
- **Manager RBAC** — additional admin accounts with permission scopes (clients-only, servers-only, support-only), audit log of who did what
- **Unlimited clients and servers**

---

## How the gating works in practice

The public repository contains the MIT open core plus marked compatibility
stubs. Official customer packages supply protected commercial implementations;
their runtime activation still depends on the signed licence feature set.

**On a FREE install:**

- `LICENSE_KEY` env var is empty.
- `LicenseManager` returns FREE tier without a licence-server heartbeat.
- Plugin loader scans `plugins/`, sees that none of the paid plugins' required features are granted, skips them all.
- The Vue admin panel hides paid-feature UI (or shows it locked, depending on which screen).
- API endpoints behind paid features return `403` with a clear upgrade hint.

**On a paid install:**

- `LICENSE_KEY` is set in `.env`.
- `LicenseManager` validates the RSA-signed key against the embedded public key. Subscription licences use online enforcement with a 72-hour outage grace window; Lifetime licences remain operational offline and use a once-daily heartbeat only for clone detection and update/support state.
- Plugin loader picks up the matching plugin manifests and mounts their routers.
- Paid feature endpoints return real responses.
- Commercial implementations such as extra protocols, multi-server orchestration, Corporate VPN, RBAC, paid automation, and third-party payment providers are not published in this MIT tree.
- An update of an already licensed installation preserves `.env`, the database,
  licence cache, signed server list, limits, and feature flags. It replaces the
  implementation/runtime tree without reactivating or reissuing the licence.

If your subscription expires or is cancelled, the paid plugins refuse to load on the next restart. Your FREE-tier features keep working unchanged.

---

## What you can still do without paying

A few things people sometimes ask about that are FREE forever:

- ✅ **Run Flirexa for personal / family use** — never going to need a license
- ✅ **Run Flirexa as a small commercial service** up to 80 clients, accepting crypto via NOWPayments
- ✅ **Fork the public repository** and modify it for your own use (MIT license)
- ✅ **Write community plugins** that extend Flirexa with new features unrelated to the paid plugins
- ✅ **Embed Flirexa in your own product** as long as you preserve the MIT copyright notice
- ✅ **Run without a paid licence heartbeat** — installer diagnostics can be disabled with `INSTALL_TELEMETRY=off`; update checks still use the signed official update service

---

## Honest trade-offs

A few things to know up front:

- **Subscription and Lifetime licences behave differently.** Subscriptions use online enforcement with a 72-hour outage grace window. Lifetime installations remain operational offline; their daily heartbeat is detection/support telemetry, not a kill switch. FREE installs are unaffected.
- **Commercial implementations are separately licensed.** The open core exposes marked compatibility stubs and feature interfaces. Official customer archives protect the commercial backend; NOWPayments and the documented FREE functionality remain in the MIT core.
- **Billing periods vary.** Monthly, annual, and lifetime options can be offered by the current checkout. Consult [flirexa.biz](https://flirexa.biz) for the combinations available for each tier.

---

## Pricing FAQ

**Why open-core instead of fully open / fully closed?**
Fully open (like 3X-UI) means donations as the only revenue, which doesn't fund full-time development for serious commercial features. Fully closed has no community and no distribution. Open-core lets the FREE core thrive on community contributions while paid plugins fund maintenance.

**Which price is current?**
The website checkout is authoritative. This document records the feature model but may lag a price promotion or billing-period change.

**Can I downgrade?**
Yes. Cancel any time. At the end of the current billing period your install reverts to FREE — clients and servers stay where they are; you just lose access to the paid features. No data loss.

**Do you offer non-profit / educational discounts?**
Email `support@flirexa.biz` to ask about eligibility.

**What happens to my data if I stop paying?**
Your clients, VPN configurations, traffic, and payment records stay on your installation. Paid licence validation sends licence/activation identifiers, a derived hardware and instance identifier, product version, status/uptime metadata, and normal request metadata such as source IP; it does not upload your client list or VPN traffic. Cancelling does not delete local data.
