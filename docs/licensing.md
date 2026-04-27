# Licensing model

How Flirexa licenses are structured: open-core MIT for the public repository, commercial licenses for paid plugins, and the trust boundary between them.

If you want a feature comparison, see [free-vs-paid.md](free-vs-paid.md). This page is about the legal and technical mechanics.

---

## Two layers of licensing

### Layer 1: Open core (MIT)

Everything in this repository is **MIT-licensed**. You can:

- Read it, run it, modify it, ship it as part of your own product.
- Use it commercially without paying anyone.
- Fork it and remove the license-feature gates. (See "Why we still have gates" below.)
- Embed Flirexa logic in proprietary products — just keep the MIT copyright notice somewhere reachable.

The full text is in [LICENSE](../LICENSE).

### Layer 2: Paid plugins (commercial)

The paid plugins distributed by the official Flirexa license server are **closed-source under a separate commercial license** tied to your active subscription. You can:

- Run them on as many installs as your subscription tier allows.
- Use them in your commercial VPN service.

You **cannot**:

- Redistribute them to others.
- Reverse-engineer them and republish as open source.
- Use them after your subscription has lapsed.

The licence server enforces these via the per-instance hardware-ID validation flow.

---

## How license activation works

When you set `LICENSE_KEY` in `/opt/vpnmanager/.env`:

1. **Local validation** — `LicenseManager` parses the key (`base64(payload).base64(signature)`), verifies the RSA-PSS signature against `data/license_public.pem` shipped with the install. If verification fails, falls back to FREE.
2. **Hardware binding** — the key payload includes a `hardware_id`. `LicenseManager` computes the local hardware fingerprint (machine-id + MAC + hostname hash) and checks it matches. If not, falls back to FREE.
3. **Online validation** — every 4 hours the `online_validator` worker contacts the license server to confirm the subscription is still active. This is the only outbound network call licensed installs make to Flirexa infrastructure (and the only one that exists at all — FREE installs make none).
4. **Plugin entitlements** — the licence server returns a list of plugin features your subscription unlocks. The plugin loader checks `LicenseManager.has_feature(...)` for each plugin and only loads ones you're entitled to.

### Failure modes

- **License server unreachable**: paid features keep working from the local cache for 72 hours, then disable themselves with a clear message. Reconnect, restart, you're back. Your FREE-tier core is unaffected throughout.
- **Subscription cancelled**: takes effect on the next online validation cycle (≤4h). Paid plugins refuse to load on the next API restart; your data stays intact.
- **License key tampered**: signature verification fails locally, install falls back to FREE silently.
- **Hardware change** (e.g. you migrated to a new server): the license refuses to validate on the new hardware. Email `support@flirexa.biz` with the new install's hardware ID and we issue a re-bound license — no extra charge for legitimate hardware migrations.

---

## What's open vs closed at the file level

### Genuinely open (in this repository, MIT, can fork freely)

```
src/api/                  All API routes, including paid-tier route gates
src/core/wireguard.py     WireGuard manager (FREE)
src/core/amneziawg.py     AmneziaWG manager (FREE)
src/core/client_manager.py
src/core/server_manager.py
src/core/traffic_manager.py
src/modules/license/      License validation client (the paid SERVER is closed)
src/modules/plugin_loader/
src/modules/payment/      Provider interface + NOWPayments
src/modules/subscription/
src/modules/health/
src/modules/updates/
src/modules/email/
src/modules/branding.py
src/modules/notifications.py
src/modules/backup_manager.py
src/web/frontend/         Admin Vue SPA
src/web/client-portal/    Client portal Vue SPA
src/bots/admin_bot.py
plugins/_example/         Reference scaffold
plugins/payments/         Drop-in payment providers
plugins/<paid>/manifest.json + __init__.py   Plugin shells (declare the gate)
```

These are the bones of the product. The MIT license here is unconditional.

### Stubs in this repository (real implementations closed)

```
src/core/hysteria2.py        STUB — real impl in flirexa-pro/extra-protocols
src/core/tuic.py             STUB
src/core/proxy_base.py       STUB
src/modules/corporate/       STUB — real impl in flirexa-pro/corporate-vpn
```

These files exist in the open repo only to keep imports working. They raise `NotImplementedError` when actually used. The real code is closed-source, distributed only through paid plugin packages.

### Genuinely closed (in `Flirexa/flirexa-pro` private repo)

```
extra-protocols/             Hysteria2 + TUIC implementations
corporate-vpn/               Site-to-site VPN implementation
src/bots/client_bot.py       Full client Telegram bot
```

These never reach the public repository.

---

## Why we still have gates on open-source code

Most paid features (multi-server, white-label, traffic rules, auto-backup, manager RBAC, promo codes, client Telegram bot) live in the open repository with route-level gates. A motivated forker can remove the gates with a few `sed` commands.

We accept this trade-off because:

1. **The bigger lift is integration, not implementation.** Removing gates gives you the code; running a stable production VPN on top of it is still work.
2. **You don't get our updates.** A fork that removes gates ships v1.5.0 forever; we ship security fixes, new protocols, new features under our subscription.
3. **You don't get the closed plugins.** Hysteria2, TUIC, and corporate VPN aren't in the public repo at all — those are protected by absence.
4. **Operating in good faith pays.** A subscription is cheaper than maintaining a fork.

This is the same trade-off Sentry, GitLab CE, and PostHog accept. The gates fund development; the paid closed plugins protect the most-fork-sensitive features.

---

## Refunds and cancellation

- **Cancel any time** through the customer portal at `flirexa.biz` (when the subscription billing system is live; if you signed up before that, email us).
- **No partial-period refunds** — your subscription stays active until the end of the current billing period, then auto-converts to FREE.
- **30-day refund** for first-time purchasers if Flirexa doesn't work for your use case. Email `support@flirexa.biz` describing the issue; we'll usually offer a fix first, but if you want out, you'll get the money back.

---

## What if Flirexa shuts down?

A reasonable concern for any commercial-software dependency. Here's the public commitment:

If we ever wind down operations, we will **release a final version of the licence server's validation logic such that all then-current paid licences become permanent**. Existing paid installs would keep working forever; new licences couldn't be issued. We won't disappear and brick your service.

We also keep the closed-source plugin source in escrow with a third party who has a contract to release it as open source if Flirexa Inc. (or whatever the legal entity is at the time) stops responding for 90 days. The arrangement protects you against the worst case.

---

## Commercial licence enquiries

For:

- **OEM licensing** (you ship Flirexa as part of a larger product)
- **White-label / re-brand** beyond what the `white-label-basic` plugin covers
- **On-prem licence server** (your installs validate against your own infrastructure)
- **Volume discounts** for hosting providers offering Flirexa as a one-click app
- **Custom plugin development** under contract

Email `support@flirexa.biz` with rough scope and timeline.
