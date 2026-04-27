# Changelog

All notable changes to Flirexa are documented here. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project follows [Semantic Versioning](https://semver.org/).

---

## [1.5.0] — 2026-04-27 — First public open-core release 🎉

This is the first release of Flirexa as an open-core project. Everything before 1.5.0 was a closed product; 1.5.0 is the cut where the codebase moved to a public MIT-licensed repository with paid plugins distributed separately.

### Why this release matters

The previous closed-source product had no public users — anonymous vendor + crypto-only payments + closed source = invisible product. Marzban, Hiddify, and 3X-UI (all open) demonstrated that operators in this niche pick open code. Flirexa is the rebuild on that foundation.

The FREE tier in 1.5.0 is a **complete, useful product on its own**:

- WireGuard + AmneziaWG protocol management
- Up to 80 clients on 1 server
- Web admin panel (Vue 3) on port 10086
- Client portal with NOWPayments crypto integration on port 10090
- Admin Telegram bot
- 6 languages (EN, RU, UK, DE, FR, ES)
- Manual backup / restore
- Auto-updates from GitHub Releases
- Generic plugin loader for license-gated premium features

A small operator running a personal VPN service for friends or a small commercial deployment never has to talk to the license server.

### Added

- **`LicenseType.FREE`** — open-core tier with 80 client / 1 server limits, never expires, makes zero network calls. New `is_free()` / `is_paid()` helpers on `LicenseManager`. Empty `LICENSE_KEY` → FREE; invalid key → graceful fallback to FREE (rather than the previous "force-trial" behaviour).
- **Generic plugin loader** (`src/modules/plugin_loader/`) with manifest validation, license-feature gating, and FastAPI router auto-mounting. Plugins live in `plugins/<name>/` with a `manifest.json` declaring `requires_license_feature`. The loader skips plugins on FREE installs without leaving traces.
- **Reusable license-gate dependency** (`src.api.middleware.license_gate.require_license_feature`). Routes that paywall a feature use it as a FastAPI `Depends(...)` — fails-closed (503) if `LicenseManager` itself errors.
- **Nine paid-plugin shells** declaring features: `extra-protocols`, `multi-server`, `corporate-vpn`, `client-tg-bot`, `traffic-rules`, `promo-codes`, `auto-backup`, `white-label-basic`, `manager-rbac`. Each carries a `manifest.json` and a status route under `/api/v1/plugins/<name>/status` for introspection.
- **Per-protocol gating** in `POST /api/v1/servers` — Hysteria2/TUIC require the `proxy_protocols` feature; FREE rejects with `403` and a clear upgrade hint.
- **Repository scaffolding for community contribution** — MIT `LICENSE`, `CONTRIBUTING.md`, `SECURITY.md`, GitHub issue templates (`bug.yml`, `feature.yml`), PR template, CI workflow with pytest + `detect-secrets`, branch protection on `main`.
- **Documentation rewrite** — all `docs/*.md` rewritten for the open-core era. New: `docs/free-vs-paid.md`, `docs/licensing.md`, `docs/plugins.md`.
- **`ROADMAP.md`** — public 3-quarter forward plan.

### Removed

- **`src/modules/integrity/sentinel.py`** and its callers (`api/main.py` startup full check + per-request spot check, `license/manager.py` cross-check beacon, `license/online_validator.py` periodic check, `build_release.sh` integrity hash injection).
  *Why?* The sentinel was an anti-piracy SHA-256 file beacon designed for the closed-source product. In open-source code anyone can recompute hashes and bypass the check, so it provided theatre rather than security. Removing it cuts ~200 lines of dead code and removes a hard dependency on the (now also removed) PyArmor obfuscation step.
- **PyArmor obfuscation** from the build pipeline. Open-source code being obfuscated is a contradiction; the protection that mattered (paid plugin source) lives in the private `flirexa-pro` repo instead.
- **License kill switch** for FREE installs. Previously the codebase could refuse to start if the license server didn't respond within 72 hours. FREE never contacts the license server now, so the failure mode is gone.
- **`src/core/{hysteria2,tuic,proxy_base}.py`** real implementations (~1700 lines) — moved to the private `flirexa-pro/extra-protocols/` repo. The public repo keeps minimal stubs that preserve import paths and raise `NotImplementedError` with an upgrade hint when instantiated.
- **`src/modules/corporate/`** real implementation — moved to `flirexa-pro/corporate-vpn/`. Same stub treatment.
- **Stub payment providers** (`btc.py`, `usdt.py`, `ton.py`) that never actually worked. Real providers live in `plugins/payments/` and ship working: NOWPayments, CryptoPay, Stripe, Mollie, Razorpay, Payme.
- **Vendor-only directories** from the public distribution: `license_server/` (vendor infrastructure), `landing/` (marketing site), `tools/make_demo_*` (vendor screen recorder), `deploy.sh` / `build_release.sh` / `package.sh` (vendor build scripts), all internal handoff docs (`PROD_SERVER.md`, `AI_ENTRYPOINT.md`, `ARCH_MAP.md`, `CHILD_NODES.md`, etc.). They live in the private repo and never get pushed to public.
- **`NEW_MODULES_CLIENT_PORTAL/`** — stale February 2026 draft superseded by `src/modules/subscription/` and `src/web/client-portal/` long ago.
- **`android-app/`** — abandoned WireGuard Android fork. Not part of the open-core product; if it returns it'll be a separate dedicated repo.
- **`VPN Management Studio/`** docs directory — duplicate of older `docs/`, no longer kept in sync.

### Changed

- **License tiers reorganised** to match the published pricing. `STARTER` / `STANDARD` get 500 clients / 1 server with the protocol + portal features that operators of that scale need. `BUSINESS` / `PRO` get 2000 clients / 10 servers with multi-server, white-label, traffic rules, auto-backup. `ENTERPRISE` keeps unlimited and adds corporate VPN, full white-label, and manager RBAC.
- **`derive_license_mode()`** now returns `"normal"` for FREE installs (previously could return `license_grace` / `license_expired_readonly` if a stale `LICENSE_KEY` env var triggered the online validator).
- **`FailSafeManager.refresh()`** stops trying to validate licenses on FREE installs. The previous code did so via a broken function call (`get_license_manager(db)` with an unsupported argument) that silently always raised, so it was effectively dead — now it's intentionally a no-op for FREE and a real check for paid.
- **All hardcoded production credentials removed** from defaults. Web panel admin credentials, deploy host, demo recorder login — all require explicit env vars now. RFC 5737 placeholder IPs (`203.0.113.x`) replaced previous hardcoded private IPs in tests.
- All references to the previous personal-account docs repo updated to point at the new `Flirexa/` organisation in landing / install scripts.

### Fixed

- Generic plugin loader middleware path mismatches: `/api/v1/promo` → `/api/v1/promo-codes` (actual route prefix), feature `payments` → `promo_codes` (actual feature flag). The old wrong values were dead-coded gates that did nothing.
- `/api/v1/bots` is no longer URL-prefix-gated by `telegram_admin_bot` — admin bot is a FREE feature; only client bot endpoints (`/bots/client/*`) are now per-route gated by `telegram_client_bot`.

### Tests

- 36 new unit + integration tests for FREE-tier behaviour, the plugin loader, and individual paid-plugin gating (`test_license_free_tier.py`, `test_free_mode_integration.py`, `test_plugin_loader.py`, `test_extra_protocols_plugin.py`, `test_multi_server_plugin.py`, `test_phase5_plugins.py`).
- Total: 580 passing tests in the development tree, 570 in the published copy (10 paid-plugin tests moved to `flirexa-pro` alongside their implementations). 26 pre-existing failures in `test_payment_flow.py` documented; unchanged by this release.

---

## Pre-1.5.0

Earlier internal versions (1.4.x and below) were the closed-source product. They are not included in this changelog because none of them shipped publicly.
