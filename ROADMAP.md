# Roadmap

What's next for Flirexa, organised by quarter. Items higher in each section are higher priority. Dates are aspirational; items move when reality intervenes.

If you'd like to see something prioritised, [open a discussion](https://github.com/Flirexa/flirexa/discussions) or vote on existing ones with 👍.

---

## 2026 Q2 — Make the open-core launch real

The repository is public, but the commercial loop isn't fully wired yet. This quarter is about closing that.

- [ ] **Subscription billing on flirexa.biz**
  Stripe Subscription for cards, recurring NOWPayments for crypto. Webhooks for renewal / cancellation / past-due. Email notifications.
- [ ] **Signed plugin distribution**
  Paid plugins (`extra-protocols`, `multi-server`, `corporate-vpn`, …) ship as RSA-signed `.tar.gz` packages from the license server. The plugin loader downloads and verifies them on startup for licensees. Today they live in the private `flirexa-pro` repo and are baked into the official installer; this formalises the channel.
- [ ] **Domain consolidation**
  Migrate active workloads onto a single primary host (`flirexa.biz`) with the previous infrastructure as failover. Reduces operational complexity for the launch period.
- [ ] **Pre-commit hooks**
  `detect-secrets`, `ruff`, `mypy` so contributors catch problems locally before CI does. CI already runs detect-secrets on PRs.

## 2026 Q3 — Make the project welcoming

- [ ] **Public demo instance**
  `demo.flirexa.biz` with the admin panel and client portal pre-populated with realistic fake data and a 6-hour automatic reset. Lets evaluators try the product before they install.
- [ ] **Plugin marketplace**
  A community-curated list of third-party plugins (notification integrations, custom payment providers, monitoring exporters, etc.). Submission via PR.
- [ ] **First community plugin examples**
  Reference plugins for Slack/Telegram alert routing and Prometheus metrics — both genuinely useful, both demonstrate the plugin API end-to-end.
- [ ] **Documentation site**
  MkDocs Material site at `docs.flirexa.biz` built from `docs/` in this repo. Same source, prettier surface.
- [ ] **Comparison content**
  In-depth blog posts and YouTube walkthroughs comparing Flirexa with Marzban, Hiddify, WG-Easy on real workloads.

## 2026 Q4 — Mobile + ecosystem

- [ ] **Mobile client app**
  Native Android (and probably iOS) app that pairs with a Flirexa install via QR, fetches configs, manages multiple endpoints. Closed-source, distributed via Play Store / TestFlight, free for end users of any Flirexa install.
- [ ] **Localisation expansion**
  Persian (Farsi), Chinese, Turkish, Spanish/Portuguese for LATAM. Driven by where the user base ends up actually being.
- [ ] **Backup-to-cloud presets**
  S3, Backblaze B2, Hetzner Storage Box — one-click destinations for the `auto-backup` plugin.

## 2027 — Beyond v1

Items that are interesting but not committed yet:

- **WireGuard inside WARP** transport for installs that need to look like ordinary HTTPS to a network observer
- **OAuth providers** (Google, GitHub) for the admin panel
- **API rate limiting** and quota tiers
- **PostgreSQL replication** support for HA installs
- **Kubernetes Helm chart** for installs that prefer cluster deployment over systemd

---

## Out of scope

To set expectations honestly, these are things Flirexa **will not** become:

- A general-purpose VPN client app for end users (use the WireGuard / AmneziaVPN apps; Flirexa is server-side)
- A V2Ray / Xray panel (Marzban already does that very well)
- A CDN or anti-DDoS service (different problem)
- A cryptocurrency exchange or payment processor (we *integrate* with NOWPayments, Stripe, etc.; we don't compete with them)

---

## Done in 1.5.0 (initial public release)

For reference — what shipped in the open-core launch:

- FREE tier with 80 clients / 1 server / no online check / no expiry
- Generic plugin loader with manifest validation and license-feature gating
- Nine paid-plugin shells declared (`extra-protocols`, `multi-server`, `corporate-vpn`, …)
- Hysteria2/TUIC and Corporate VPN implementations extracted to private `flirexa-pro` repo
- PyArmor / `integrity` / kill-switch removed from open core
- MIT license, CONTRIBUTING.md, SECURITY.md, CI workflow
- 580 passing tests; pre-existing failures documented
