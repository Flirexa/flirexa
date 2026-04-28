# FREE vs paid

Honest, unhedged answer to "what do I get for free and what do I have to pay for?"

If you're choosing between Flirexa and an alternative, this page is the comparison ammunition. If you're already running Flirexa and wondering whether to upgrade, this page tells you what unlocks at each tier.

---

## TL;DR

**FREE** is a complete VPN service for one operator on one server with up to 80 clients. WireGuard + AmneziaWG, panel, client portal, crypto payments via NOWPayments, Telegram admin bot, manual backups. MIT-licensed, install once, run forever — no payment, no expiry.

**Starter ($19/mo)** adds Hysteria2, TUIC, promo codes, auto-renewal.

**Business ($49/mo)** adds multi-server, white-label, traffic rules, scheduled backups, full client Telegram bot.

**Enterprise ($149/mo)** adds site-to-site corporate VPN, full white-label (custom domain, custom email sender), and multi-admin RBAC.

---

## What's in FREE forever

| | |
|---|---|
| **Protocols** | WireGuard, AmneziaWG |
| **Clients** | up to 80 |
| **Servers** | 1 |
| **Admin panel** | full Vue 3 SPA on port 10086 |
| **Client portal** | full Vue 3 SPA on port 10090 with self-service signup, plans, payment, config download |
| **Telegram admin bot** | full functionality |
| **Telegram client bot** | not available (Business+ feature) |
| **Crypto payments** | NOWPayments built-in (BTC, ETH, USDT, XMR, +50 more) |
| **Other payment providers** | not in FREE — Stripe / Mollie / Razorpay / Payme / PayPal ship as paid plugins (Business tier or higher) |
| **Languages** | EN, RU, DE, FR, ES |
| **Manual backup / restore** | yes |
| **Scheduled backups** | not available (Business+ feature) |
| **Auto-updates** | yes, from GitHub Releases |
| **License check** | none — FREE installs never contact a license server, never expire, and cannot be remotely disabled |
| **Source code** | all of it, MIT-licensed |

### Limits in numbers

- **80 clients per install**: enforced by the API, not just a soft suggestion. If you hit 80, you cannot add a 81st without upgrading or deleting an existing one.
- **1 server per install**: the multi-server orchestration code is loaded only with the `multi-server` plugin. The API rejects creating a 2nd server with `403`.
- **WireGuard endpoint count**: a single WireGuard interface can host all 80 clients comfortably.

---

## Starter — $19 / month

For solo operators who started monetizing and outgrew the FREE protocol set or want acquisition tools.

**Adds:**

- **Hysteria2** support — QUIC-based proxy, censorship-resistant
- **TUIC** support — alternative QUIC proxy, useful when Hysteria2 is fingerprinted
- **Promo codes** — percent-off, free-day extensions, tier-restricted, expiring
- **Auto-renewal** — reminder emails N days before expiry, optional auto-charge
- **Up to 300 clients** (vs 80 on FREE)

Stays on **1 server**.

**Why $19:** that's less than a single day's revenue from a small VPN operator. It's the smallest amount that filters "doing this seriously" from "running this for fun."

---

## Business — $49 / month

The headline-feature tier. This is what serious commercial operators actually pay for.

**Adds:**

- **Multi-server orchestration** — manage up to 10 servers from one panel. Push clients to specific servers, balance load, see per-server traffic. Remote VPN nodes run a tiny `vpnmanager-agent` HTTP service.
- **Full client Telegram bot** — end users can register, browse plans, pay in crypto, download configs, all via Telegram. Most operators in Russia / Iran / Turkey markets prefer this over the web portal.
- **Traffic rules** — per-client and global throttling, automatic enforcement when a quota threshold is hit
- **White-label (basic)** — replace the Flirexa logo, change brand colors, remove the "Powered by Flirexa" footer attribution
- **Scheduled backups** — daily automatic backups; mount remote storage (S3, FTP, NFS, SMB); retain N revisions
- **Up to 2,000 clients** across up to 10 servers

**Why $49:** for a Business-tier customer the price is ~1–2% of monthly revenue. It pays for itself within hours of automatic billing reminders alone.

---

## Enterprise — $149 / month

For ISPs, MSPs, and companies who don't run an end-user VPN service but need site-to-site connectivity.

**Adds:**

- **Corporate VPN (site-to-site)** — multi-site WireGuard mesh with subnet allocation, full-mesh routing, per-site config generation, network diagnostics. The use case is "branch-office connectivity": three offices in different cities, all employees on a private VPN, traffic routed peer-to-peer through Flirexa-managed config.
- **Full white-label** — custom domain on the client portal, custom `From` address on outbound emails, custom favicon and browser tab title
- **Manager RBAC** — additional admin accounts with permission scopes (clients-only, servers-only, support-only), audit log of who did what
- **Unlimited clients and servers**

**Why $149:** the corporate-VPN feature alone replaces commercial products like OpenVPN Cloud / ZeroTier / Pritunl that charge $200–$500/month for equivalent capability.

---

## How the gating works in practice

You don't need a separate installer. Every Flirexa install ships with the same code — the difference is whether the license server granted you specific feature flags.

**On a FREE install:**

- `LICENSE_KEY` env var is empty.
- `LicenseManager` returns FREE tier with no network call.
- Plugin loader scans `plugins/`, sees that none of the paid plugins' required features are granted, skips them all.
- The Vue admin panel hides paid-feature UI (or shows it locked, depending on which screen).
- API endpoints behind paid features return `403` with a clear upgrade hint.

**On a paid install:**

- `LICENSE_KEY` is set in `.env`.
- `LicenseManager` validates the RSA-signed key against the local public key, then heartbeats with the license server to check for revocation. Local cache + 72-hour grace period mean a license-server outage doesn't break paid customers' running installs.
- Plugin loader picks up the matching plugin manifests and mounts their routers.
- Paid feature endpoints return real responses.
- For `extra-protocols` (Hysteria2/TUIC) and `corporate-vpn` specifically, the actual implementation files are not in the public repository at all — the official `install.sh` overlays them from the closed-source `flirexa-pro` package after license validation.

If your subscription expires or is cancelled, the paid plugins refuse to load on the next restart. Your FREE-tier features keep working unchanged.

---

## What you can still do without paying

A few things people sometimes ask about that are FREE forever:

- ✅ **Run Flirexa for personal / family use** — never going to need a license
- ✅ **Run Flirexa as a small commercial service** up to 80 clients, accepting crypto via NOWPayments
- ✅ **Fork the public repository** and modify it for your own use (MIT license)
- ✅ **Write community plugins** that extend Flirexa with new features unrelated to the paid plugins
- ✅ **Embed Flirexa in your own product** as long as you preserve the MIT copyright notice
- ✅ **Self-host without contacting Flirexa servers** — FREE makes zero network calls

---

## Honest trade-offs

A few things to know up front:

- **Paid features rely on the license server.** If you lose connection to `flirexa.biz` for more than 72 hours, paid plugins disable themselves. This is intentional — it's how subscription validation works. FREE installs are not affected.
- **Paid plugins for Hysteria2/TUIC and corporate VPN are genuinely closed-source.** The implementations are not in the public repository. Forks of the public repo cannot trivially access them. (Other paid plugins live in the public repo as gates over public code; that's a smaller protection but covers the most-fork-sensitive features.)
- **One-time / lifetime licenses are not offered.** All paid tiers are monthly subscriptions. If recurring billing isn't an option for you, contact `support@flirexa.biz` — case-by-case annual upfront pricing is available.

---

## Pricing FAQ

**Why open-core instead of fully open / fully closed?**
Fully open (like 3X-UI) means donations as the only revenue, which doesn't fund full-time development for serious commercial features. Fully closed has no community and no distribution. Open-core lets the FREE core thrive on community contributions while paid plugins fund maintenance.

**Why these prices?**
Calibrated against operator revenue: Starter is less than a day of a small operator's earnings; Business is ~1–2% of MRR for a 500-client service; Enterprise is dramatically cheaper than commercial site-to-site VPN alternatives.

**Can I downgrade?**
Yes. Cancel any time. At the end of the current billing period your install reverts to FREE — clients and servers stay where they are; you just lose access to the paid features. No data loss.

**Do you offer non-profit / educational discounts?**
Yes — email `support@flirexa.biz`. We've handled this case-by-case successfully before.

**What happens to my data if I stop paying?**
Nothing — Flirexa never had your data. Your clients, servers, and payment records all live on your install. The license server only knows your hardware ID and active feature set. Cancel and your data stays exactly where it is, you just can't use the paid features anymore.
