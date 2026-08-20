# Roadmap

_Last verified: 2026-07-30_

What's next for Flirexa, organised by quarter. Items higher in each section are higher priority. Dates are aspirational; items move when reality intervenes.

If you'd like to see something prioritised, [open a discussion](https://github.com/Flirexa/flirexa/discussions) or vote on existing ones with 👍.

---

## 2026 Q3 — Distribution and community

- [ ] **Signed plugin distribution**
  Move from the current universal protected customer archive to authenticated,
  integrity-checked, entitlement-specific commercial bundles. The public tree
  contains compatibility stubs; the readable commercial implementation source
  remains in the private repository.
- [ ] **Settlement-backed end-customer renewal**
  Restore optional client-portal auto-renewal only after each added paid period
  consumes one newly verified provider settlement through an idempotent flow.
  Manual checkout and renewal remain the supported path until then.
- [ ] **Plugin marketplace**
  A community-curated list of third-party plugins (notification integrations, custom payment providers, monitoring exporters, etc.). Submission via PR.
- [ ] **First community plugin examples**
  Reference plugins for Slack/Telegram alert routing and Prometheus metrics — both genuinely useful, both demonstrate the plugin API end-to-end.
- [ ] **Documentation site**
  MkDocs Material site at `docs.flirexa.biz` built from `docs/` in this repo. Same source, prettier surface.
- [ ] **Comparison content**
  In-depth blog posts and YouTube walkthroughs comparing Flirexa with Marzban, Hiddify, WG-Easy on real workloads.

## 2026 Q4 — Apps and ecosystem

- [ ] **iOS client app**
  An iOS companion to the Android, Windows, and Linux apps already distributed to Enterprise customers.
- [ ] **Localisation expansion**
  Persian (Farsi), Chinese, Turkish, and Portuguese for LATAM. Driven by where the user base ends up actually being. (English, Русский, Deutsch, Français, and Español already ship.)
- [ ] **Backup-to-cloud presets**
  S3, Backblaze B2, Hetzner Storage Box — one-click destinations for the `auto-backup` plugin.

## 2027 — Longer-term ideas

Items that are interesting but not committed yet:

- **WireGuard inside WARP** transport for installs that need to look like ordinary HTTPS to a network observer
- **OAuth providers** (Google, GitHub) for the admin panel
- **Broader API rate limiting** and quota tiers beyond the current login,
  registration, support, checkout, FCM, and subscription-link protections
- **PostgreSQL replication** support for HA installs
- **Kubernetes Helm chart** for installs that prefer cluster deployment over systemd

---

## Out of scope

To set expectations honestly, these are things Flirexa **will not** become:

- A general-purpose VPN client app for end users (use the WireGuard / AmneziaVPN apps; Flirexa is server-side)
- A general-purpose V2Ray / Xray panel (Flirexa uses Xray for VLESS-Reality, but does not aim to replace Marzban)
- A CDN or anti-DDoS service (different problem)
- A cryptocurrency exchange or payment processor (we *integrate* with NOWPayments, Stripe, etc.; we don't compete with them)

---

## Done in 2026 Q2 (open-core launch)

Wiring up the commercial loop after the repository went public:

- **Subscription billing on flirexa.biz** — recurring subscriptions for all paid tiers, payable by **card / fiat** (Visa/Mastercard, Apple Pay, Google Pay, bank transfer in USD/EUR via PayLio) *or* in **crypto** via NOWPayments (BTC, USDT, Monero, ETH, and 50+ currencies). Webhooks for renewal / cancellation / past-due, plus email notifications.
- **Pre-commit hooks** — `detect-secrets`, `ruff`, `mypy` so contributors catch problems locally before CI does.
- **Public interactive demo** — realistic fake data lets evaluators try the admin and client experiences before installing.
- **Client apps** — Android, Windows, and Linux apps are available to Enterprise customers.

## Done in 1.5.0 (initial public release)

For reference — what shipped in the open-core launch:

- FREE tier: 80 clients with one local WireGuard and one local AmneziaWG server,
  MIT-licensed, with no license key or expiry
- Generic plugin loader with manifest validation and license-feature gating
- Paid-plugin declarations and deterministic public compatibility stubs for
  closed commercial implementations
- Hysteria2/TUIC/VLESS-Reality, Corporate VPN, multi-server, traffic, payment,
  branding, app, and other paid implementations maintained in the private
  source inventory and compiled in official customer archives
- Legacy PyArmor / `integrity` / kill-switch removed from open core; official customer builds use the separate Cython/Nuitka native pipeline
- MIT license, CONTRIBUTING.md, SECURITY.md, CI workflow
- Automated tests and secret scanning in public CI
