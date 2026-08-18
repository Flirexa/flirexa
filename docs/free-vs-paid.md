# FREE vs paid

_Last verified: 2026-08-18. Current checkout pricing on [flirexa.biz](https://flirexa.biz) is authoritative._

Honest, unhedged answer to "what do I get for free and what do I have to pay for?"

If you're choosing between Flirexa and an alternative, this page is the comparison ammunition. If you're already running Flirexa and wondering whether to upgrade, this page tells you what unlocks at each tier.

---

## TL;DR

**FREE** is a complete VPN service for one operator on one physical host with up to 80 clients. WireGuard + AmneziaWG, panel, client portal, crypto payments via NOWPayments, Telegram admin bot, manual backups. MIT-licensed, install once, run forever — no payment, no expiry.

**Starter (from $12/mo)** adds Hysteria2/TUIC/VLESS-Reality protocols and promo codes.

**Business (from $49/mo)** adds multi-server, traffic rules, scheduled backups,
the full payment-provider suite, the full client Telegram bot, prepaid customer
credit, and four per-device DNS protection modes.

**Enterprise (from $149/mo)** adds site-to-site corporate VPN, all built-in
appearance and white-label controls, multi-admin RBAC, the standard client-app
package, custom DNS profiles, and enforced DNS policies.

These plan descriptions apply to newly issued licences. An older paid key keeps
any capability explicitly present in its signed feature set; updates do not
silently remove a previously purchased flag.

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
| **Languages** | EN, RU, UK, DE, FR, ES |
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
- **Up to 500 clients** (vs 80 on FREE)

Automatic end-customer subscription renewal is temporarily unavailable. The
portal uses manual renewal until every added paid period can be tied to one
newly verified provider settlement. Existing signed entitlements are preserved
for a compatible replacement.

Runs the enabled protocols on the install host. Remote-node orchestration starts at Business.

---

## Business — from $49 / month

The headline-feature tier. This is what serious commercial operators actually pay for.

**Adds:**

- **Multi-server orchestration** — manage up to 10 servers from one panel. Push clients to specific servers, balance load, see per-server traffic. Remote VPN nodes run a tiny `vpnmanager-agent` HTTP service.
- **Full client Telegram bot** — end users can register, browse plans, pay in crypto, download configs, all via Telegram. Many operators in censorship-heavy and crypto-native markets prefer this over the web portal.
- **Traffic rules** — per-client and global throttling, automatic enforcement when a quota threshold is hit
- **Scheduled backups** — daily automatic backups; mount remote storage (S3, FTP, NFS, SMB); retain N revisions
- **Customer account balance** — customers can add prepaid USD credit through
  a configured provider and use it for later subscription purchases; operator
  adjustments require a reason and are audit-logged
- **Per-device DNS protection** — configure no-filter, ads/trackers, malware,
  and combined resolver modes, then optionally let each portal customer choose
  a mode for every device
- **Up to 2,000 clients** across up to 10 servers

---

## Enterprise — from $149 / month

For ISPs, MSPs, and companies who don't run an end-user VPN service but need site-to-site connectivity.

**Adds:**

- **Corporate VPN (site-to-site)** — multi-site WireGuard mesh with subnet allocation, full-mesh routing, per-site config generation, network diagnostics. The use case is "branch-office connectivity": three offices in different cities, all employees on a private VPN, traffic routed peer-to-peer through Flirexa-managed config.
- **Full white-label** — product/company names, logos, colours, footer, custom portal/admin domains, custom `From` identity, favicon, browser title, and customer Privacy/Terms links or hosted branded legal pages
- **Manager RBAC** — additional admin accounts with permission scopes (clients-only, servers-only, support-only), audit log of who did what
- **Advanced DNS policy** — create custom resolver profiles and enforce one by
  subscription plan, customer segment, portal customer, or device
- **Standard client apps** — Android, Windows, and Linux application package
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
- FREE/trial may open the native support action from the current admin header;
  no legacy reminder opens on a timer.

**On a paid install:**

- `LICENSE_KEY` is set in `.env`.
- `LicenseManager` validates the RSA-signed key against the embedded public key. Subscription licences use bounded online enforcement. Lifetime is perpetual and periodically rotates a hardware-, instance-, and licence-bound signed offline lease valid for at most 30 days.
- Plugin loader picks up the matching plugin manifests and mounts their routers.
- Paid feature endpoints return real responses.
- Purchased tiers render no Flirexa donation control or modal. Enterprise can
  also remove project attribution through its white-label controls.
- Commercial implementations such as extra protocols, multi-server orchestration, Corporate VPN, RBAC, paid automation, and third-party payment providers are not published in this MIT tree.
- An update of an already licensed installation preserves `.env`, the database,
  licence cache, signed server list, limits, and feature flags. It replaces the
  implementation/runtime tree without reactivating or reissuing the licence.

If your subscription expires or is cancelled, paid capabilities stop loading.
Your local data remains on the installation and the FREE-tier capabilities keep
working.

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

- **Lifetime is perpetual and outage-tolerant, not a reusable static unlock.**
  It includes future standard product updates and a hardware-, instance-, and
  licence-bound signed offline lease valid for up to 30 days after successful
  validation. FREE installs remain independent of the licensing service.
- **Commercial implementations are separately licensed.** The open core
  exposes marked compatibility boundaries and feature interfaces. Official
  customer releases protect the commercial backend; NOWPayments and the
  documented FREE functionality remain in the MIT core.
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
