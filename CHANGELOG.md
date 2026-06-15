# Changelog

All notable changes to Flirexa are documented here.

---

## v1.9.92 — 2026-06-15

Consolidated release covering a full bug-audit sweep plus UI polish since v1.9.73.

### Fixed

- **Stored XSS in the dashboard map.** Server/client names and other fields were
  interpolated raw into Leaflet popup HTML; a client named with an `<img onerror>`
  payload could run script in the admin panel. All interpolated values are now
  HTML-escaped.
- **Server health alerts were silently disabled.** A duplicate `_record_state`
  override called a non-existent state-store method (the error was swallowed), so
  the anti-flapping state machine and Telegram/portal down-alerts never fired.
  Removed the bad override — server/agent down alerts work again.
- **Traffic double-counting.** A peer transiently absent from `wg show`
  (pre-handshake, interface just restarted) was read as `(0,0)`, which rebased the
  baseline to zero and double-counted the peer's whole counter on the next sync.
  Absent peers are now skipped without touching the baseline.
- **AmneziaWG peers lost on restart.** `save_config` used a bare interface name
  instead of the full config path, so runtime peer add/remove never persisted to
  disk and vanished on the next `awg-quick down/up`.
- **Telegram client bot leaked a DB session on every device-add** (a wrong
  `close()` call); added a global error handler to the bot.
- **Device-limit over-allocation (TOCTOU).** Concurrent add-device requests could
  exceed `max_devices`; the count-then-create is now serialized with a per-user
  advisory lock.
- **Frontend lifecycle/race fixes:** leaked intervals and object URLs, poll races
  clobbering fresher data, double-submit on payment actions, money values now
  rendered with two decimals, debounced search.
- **Hysteria2/TUIC config generation** broke on IPv6 endpoints (`split(":")`);
  fixed with a bracket-aware host parser. Hysteria2 now fails loudly on an
  unresolved server auth password instead of emitting a non-connecting URI.
- **Installer:** the self-signed web-setup path now generates the nginx
  `ssl_dhparam` file, fixing fresh installs where HTTPS stayed down (`nginx -t`
  failed) while services were up.
- **Update apply** now extracts release tarballs with `filter="data"`.

### Changed

- Clients and Portal Users views: dialogs are centered, scrollable, and go
  full-screen on small screens; the config block no longer overflows; payment and
  subscription statuses are localized across all five languages.
- Settings: added an update-channel switch (stable/test), defaulting to stable.

---

## v1.9.73 — 2026-06-07

### Fixed

- **Red "Request timed out" toast spam when multiple operators share
  the panel.** Five admin views had `setInterval(...)` poll loops
  that fired axios calls without bracketing them through
  `setBackgroundPoll(true/false)` — so a single slow agent on any one
  tick fired the global error interceptor's "Request timed out" toast
  on every operator's screen, even though the request would have
  succeeded a second later. The same toast doubles every time another
  operator joins the panel (their polls overlap with yours). New
  `silentPoll(fn)` helper in `api/index.js` brackets a single async
  tick the way the existing `useLivePoll` composable already does for
  Clients / Online Users. Applied to:
  - `Servers.vue` 5s bandwidth fan-out poll (the loudest one — fires
    every 5s, hits every server's agent)
  - `Navbar.vue` 60s update-badge poll + 30s agent-breaker counter
  - `Dashboard.vue` 30s map data refresh
  - `SystemHealth.vue` 60s component poll
  - `ServerMonitoring.vue` 60s aggregate poll
  - `Updates.vue` 60s self-healing background refresh

  Genuine failures (5xx responses, hard network drops) still surface
  the toast for explicit user actions — silentPoll only suppresses
  the periodic background ticks where a one-off slow agent already
  recovers on the next cycle.

---

## v1.9.72 — 2026-06-06

### Fixed

- **Admin Servers tab blank-white when any server has an open agent
  circuit breaker.** Two latent bugs in `Servers.vue` started firing
  together as soon as a real broken-agent appeared:
  - The agent-unreachable banner used `$tc` (vue-i18n v8 plural API)
    which doesn't exist on the v9 composition-mode template proxy,
    so the moment `brokenAgents.length > 0` the render threw a
    `TypeError: $tc is not a function` and the entire grid stopped
    painting. Switched to `$t(key, count, params)` which v9 supports
    natively.
  - The `newServer` `ref({...})` was declared ~100 lines after four
    `watch(() => newServer.value.X, …)` watchers that referenced it.
    Vue calls each watch source-fn once during setup to track
    dependencies — accessing `newServer` in the TDZ threw
    `Cannot access 'newServer' before initialization` on initial
    render. Moved the declaration up so the watchers see a real ref.

  Either bug alone could blank the page; the combination is why
  even refreshing/relogging-in didn't recover the view. Operators
  saw a working sidebar and header with a fully white content area.

---

## v1.9.71 — 2026-06-06

### Added

- **Operator-defined subscription duration ladders.** A new
  `pricing_tiers` column on `subscription_plans` lets the admin
  define an arbitrary list of `(days, price_usd, label)` entries
  per plan, replacing the hard-coded 30/90/365-day buttons in the
  customer checkout. Examples the admin can now ship without code
  changes: 2-month / 6-month / 18-month / 2-year / 5-year tiers,
  trial periods, multi-device-tier ladders. Schema migration is
  alembic `045_pricing_tiers` (JSONB on Postgres, JSON on SQLite).

  - Backend: `tariffs.py` CRUD accepts a validated `pricing_tiers`
    list (max 12 entries, days 1..3650, price ≥ 0); customer
    `/portal/v1/subscription/plans` echoes the list as-is.
    `create-invoice` validates the requested `duration_days`
    against the ladder when set — submitting a duration that
    isn't in the list returns 400 instead of guessing a prorated
    price.
  - Admin UI: `Subscriptions.vue` plan editor gained a "Custom
    durations" group between Pricing and Limits — add/remove rows
    inline with day count + price + free-form label fields.
  - Customer UI: `PaymentModal.vue` renders the custom ladder
    verbatim when present, falls back to the legacy
    1-month / 3-month / 1-year buttons when the plan ships no
    `pricing_tiers`. `duration_days` API cap raised 365 → 3650
    to accommodate multi-year prepay.

  Backwards-compatible: existing plans keep working with the
  legacy `price_monthly_usd` / `price_quarterly_usd` /
  `price_yearly_usd` columns until the operator opts in to the
  ladder.

---

## v1.9.70 — 2026-06-06

### Security & Correctness — customer-portal sweep

A multi-angle audit of `/portal/v1/*` and the Vue SPA produced a stack
of fixes for the customer-facing surface. None of these are reactive
to a customer report; all are pre-emptive hardening.

- **Webhook idempotency** for NowPayments / PayLio / CryptoPay / PayPal:
  `get_payment_by_invoice(for_update=True)` now serialises concurrent
  webhook deliveries for the same invoice at the row level, on top of
  the existing `with_for_update()` inside `complete_payment` itself
  (defence in depth — both layers are independently sufficient).
- **CryptoPay underpayment**: the previous 1% under-tolerance has been
  removed. Webhook amounts must meet or exceed the invoiced amount.
- **Promo code race**: invoice-creation now takes a row lock on the
  promo before reading `is_valid`, and `complete_payment` increments
  `used_count` via a conditional atomic UPDATE so two concurrent
  redemptions of a one-use code can no longer both apply the discount.
- **Email enumeration on register** is closed. Email-collision and
  username-collision now return the same generic "An account with
  this email or username already exists" message; the actual cause
  is still in the operator log.
- **Password reset token** lookup runs under `with_for_update()` so a
  duplicate reset attempt for the same token serialises and the
  second one finds the token already nulled out instead of racing.
- **Legacy webhook plugin path** (`process_webhook(data)` single-arg)
  is now refused with 501 instead of accepting the payload without
  signature verification — plugins must upgrade to the new
  `process_webhook(body, headers)` API.
- **Forgot-password rate limit** moved to a separate bucket so reset
  spam against a victim's email no longer consumes the IP's
  login-bucket quota.
- **Payment provider exceptions** no longer echo raw `str(e)` to the
  client — generic "Payment provider error" with full exception
  logged server-side.
- **Password field length** unified at 8–128 chars across register
  and change/reset (was 100 on register only).
- **i18n parity**: the auth section keys that en/ru carried but
  es/fr/de did not are now backfilled. The i18n loader is
  explicitly configured to silently fall back to en in production
  and to warn on missing keys in dev so future drift surfaces fast.
- **Devices.vue cooldown timers** track each slot's setInterval
  handle, replace stale ones on re-trigger, and clear them all on
  component unmount — fast region-switching used to leak parallel
  tickers.
- **PaymentModal**: crypto-amount step now carries an exchange-rate
  disclaimer. If a promo code becomes invalid between validate-time
  and invoice-creation, the local promo state is reset cleanly so
  the modal isn't stuck on a stale discount.
- **Plans.vue**: dropped the dead "Free Plan" button branch — the
  Free-tier case is already handled above as a disabled "Current
  plan" / "Free tier" button.
- **Login.vue a11y**: form errors are now associated with their
  inputs via `aria-describedby` + `aria-invalid` so screen readers
  announce them.

### Known follow-up
- The access token still lives in `localStorage`, not in an httpOnly
  cookie. Migration requires CSRF-token plumbing and a refresh-token
  endpoint and is tracked separately rather than bundled with this
  release.

---

## v1.9.69 — 2026-06-05

### Added

- **`endpoint_host` on the customer servers list.** `GET /portal/v1/servers`
  now emits the public host of each server's WG/AWG endpoint so a
  native mobile/desktop client can run its own TCP-connect probe and
  show a ping that matches the device's own network path. Previously
  the only ping signal was the panel→server `/probe` RTT, which is
  unrelated to the customer's actual route and routinely off by
  hundreds of ms. No new info is leaked — the host was already in the
  wg-quick config the customer downloaded to connect. Apps fall back
  to `/probe` when the field is absent (older panels).

---

## v1.9.68 — 2026-06-05

### Fixed

- **i18n for the new client-name field + cached-servers banner.**
  1.9.66 added the stale-cache banner on the Servers tab and 1.9.67
  added the Name input to the client Edit dialog, but both shipped
  with English-only inline fallbacks instead of real i18n keys. This
  release adds `clients.nameLabel`, `clients.namePlaceholder`,
  `servers.cacheBannerTitle`, `servers.cacheBannerBody`, and
  `common.retry` to all five locales (en / ru / es / fr / de).

---

## v1.9.67 — 2026-06-05

### Added

- **Client rename in the admin Edit dialog.** The Edit modal now has
  a Name field at the top — change the label, click Save, the WG peer
  is renamed in place (key + IP unchanged, no client reconfig needed).
  Backend already supported `name` on the `PUT /clients/{id}` payload;
  this just wires it through the existing Edit form so operators stop
  needing `psql` to clean up auto-generated names.

---

## v1.9.66 — 2026-06-05

### Fixed

- **Servers tab stays usable when a server is dead.** Three defences
  layered together: (1) `/api/v1/servers` now serialises rows one by
  one — a single corrupt row gets skipped + logged instead of nuking
  the whole response. (2) The Servers Pinia store caches the last
  successful list in `localStorage`; if a refresh 5xx's on first load,
  the cached list renders with a "Showing cached list — API
  unreachable" banner so operators still see (and can delete) every
  server. (3) `server_manager.delete_server` no longer hard-fails when
  `_get_wg()` itself blows up — with `force=true` it falls through to
  DB-only delete, matching the operator's "I want this row gone"
  intent. Backed by a new `POST /servers/{id}/purge` route that the
  panel offers as a one-click "purge from panel" fallback when even
  the normal force-delete errors out, instead of dropping the operator
  to `psql`.

---

## v1.9.62 — 2026-06-04

### Fixed

- Admin Clients tab: typing into the search box now keeps the
  filtered view visible across the 15s live-poll cycle. The poll
  used to call `store.fetchClients()` with no arguments, dropping
  the active `?q=` and reloading the full list under the search
  results within seconds. Same fix covers the bulk-action follow-up
  refetches and the on-mount load — every refetch reads the current
  `search` ref via a single helper so the textbox is always the
  source of truth.

---

## v1.9.61 — 2026-06-02

### Fixed

- **`last_good_health_at` actually gets stamped now.**
  `ServerHealthChecker._record_state` had two definitions inside the
  same class body. Python honours the LAST one, so a later refactor
  that added a lighter override silently shadowed the stamping logic
  and the timestamp stayed NULL forever for every server. Auto-hide
  and admin "agent healthy" badges both read that field — every panel
  in the field was decorating servers as "agent unhealthy" despite
  live agents responding 200 on /health. Move the stamp into the
  surviving override and switch to a fresh per-call `SessionLocal`,
  because `check_all` fires this from `ThreadPoolExecutor` workers
  and the original `self._db` share-across-threads was already a
  SQLAlchemy thread-safety violation that would have failed the
  commit even without the dead-code shadow.

---

## v1.9.60 — 2026-06-02

### Fixed

- **Delete server no longer hangs the panel on a dead remote.** Remote-side
  cleanup (WG peer removal, interface stop, agent uninstall) is now
  bounded by a 15s time budget. Once exhausted, the remaining remote
  ops skip with a logged warning and the DB delete proceeds. The
  previous flow could spend 50+ seconds blocked when a remote went
  unreachable (per-call timeouts × N clients), with the operator
  staring at a hung UI.
- **Traffic-sync circuit breaker.** When a server's `get_all_peers()`
  raises, the traffic-sync worker now suspends sync for that server
  for 10 minutes instead of hammering it every cycle. A single dead
  remote with N clients used to produce N error log lines per cycle
  indefinitely. A successful re-fetch heals the breaker.

---

## v1.9.59 — 2026-06-01

### Fixed

- Admin Clients tab now searches via the backend (`/clients?q=`). The
  page used to load the first 500 rows alphabetically and filter
  `name` / `ipv4` client-side, which silently hid peers past the
  500-row cap once a panel grew past that many clients across its
  servers. A live, traffic-flowing peer would show up in the server
  card's TOP CONSUMERS list (agent-side data) while the Clients tab
  returned "No clients found" for the same name — operator report
  from the field with 800+ clients.

  Backend: `/clients` accepts `?q=` and filters by `name` / `ipv4`
  ILIKE substring in SQL. Frontend: debounces the search box (250ms),
  forwards `q` to the endpoint, drops the local name/ipv4 filter,
  keeps status / server filters local.

---

## v1.9.58 — 2026-06-01

### Changed

- Referral tooltip now notes that the referrer needs an active paid
  subscription themselves when their friend pays — the +7-days bonus
  extends `expiry_date`, so it has nothing to attach to on a free-tier
  account and gets silently dropped. Updated across en/ru/es/de/fr.

---

## v1.9.57 — 2026-06-01

### Changed

- Client portal payment modal step 2 no longer shows the bottom
  currency picker. Every shipped provider (Stripe / Mollie /
  Razorpay / Payme / PayLio / NOWPayments / PayPal / CryptoPay)
  opens its own hosted checkout where the customer picks the actual
  coin / card / fiat — the client-side picker was redundant and was
  pre-seeding `currency=USDT` for NOWPayments, breaking availability
  lookup on the hosted page. Replaced with a single "Pay by card ·
  <Provider Name>" summary and `selectedCurrency` is hardcoded to
  USD; the backend handles per-provider quirks.

---

## v1.9.56 — 2026-06-01

### Fixed

- NOWPayments invoice now sets `price_currency` to a fiat code (USD/EUR)
  instead of forwarding the customer's crypto pick verbatim. The
  PaymentModal seeds `selectedCurrency='USDT'` for the NOWPayments
  provider; the route was passing `currency='USDT'` straight through to
  `price_currency`, which NOWPayments interprets as "this invoice
  costs 4 USDT" and runs its hosted-checkout availability lookup
  against the wrong base. Every coin then showed up as "This currency
  is currently unavailable. Try it in 2 hours" on the hosted checkout.
  The customer's crypto pick is now forwarded as `pay_currency` so the
  hosted page still lands on the right coin's address.

---

## v1.9.55 — 2026-06-01

### Fixed

- NOWPayments invoice POST now sends real `success_url` / `cancel_url`
  (derived from `CLIENT_PORTAL_URL` or the bare `CLIENT_PORTAL_DOMAIN`)
  instead of empty strings. Previously every invoice 400'd with
  "success_url is not allowed to be empty" — NOWPayments validates URL
  fields and rejects `""`, so the route now passes the portal root
  (`/?paid=1` / `/?paid=0`) and the provider omits any URL field that
  is still empty so misconfigured panels degrade to dashboard defaults
  rather than erroring out.

---

## v1.9.54 — 2026-06-01

### Fixed

- NOWPayments invoice POST no longer sends `"order_id": null`. The
  create-invoice route was passing `order_id=None` in metadata to let
  the provider default to the generated id, but `meta.get("order_id",
  fallback)` returns the explicit None instead of the fallback when the
  key is present — so the body shipped a JSON null and NOWPayments
  rejected with "order_id must be one of [string, number, object]".
  Fixed on both sides: the route omits the key, and the provider uses
  `or invoice_id` so an explicit-None still falls back.

---

## v1.9.53 — 2026-06-01

### Fixed

- Client portal NOWPayments path now uses the hosted-checkout
  `NOWPaymentsProvider` (POST `/v1/invoice` + `ipn_callback_url`)
  matching what the create-invoice route expects. Previously the portal
  process loaded the legacy `CryptoPaymentProvider` (POST `/v1/payment`,
  reads `metadata["callback_url"]`), so every customer payment failed
  with "API error: ipn_callback_url must be a string" — the legacy
  class looked for a metadata key the create-invoice flow never sets,
  serialised `null`, and NOWPayments rejected the request. The API
  service already used the new class; this aligns both processes.

---

## v1.9.52 — 2026-06-01

### Reverted

- Client portal router no longer bounces unauthenticated visitors to
  `/register`. Defaults back to `/login` (the original behaviour) — the
  redirect-to-register guard was too aggressive for returning customers
  who only wanted to sign back in. The `?next=` deep-link preservation
  is kept either way, so marketing-landing "Choose plan" links still
  route correctly after auth.

---

## v1.9.51 — 2026-06-01

First fiat-acquirer payment provider plus a few rollout fixes that came
out of the first end-to-end test on a real customer flow.

### Added

- **PayLio payment provider.** Auto-loaded plugin in
  `plugins/payments/paylio_provider.py`. Customers pay with Visa /
  Mastercard / Apple Pay / Google Pay / SEPA; the operator receives
  USDC on Polygon at `PAYLIO_PAYOUT_ADDRESS`. PayLio's IPN is an
  unsigned HTTP GET (`?ipn_token=…`), so the plugin re-verifies every
  callback against `/api/v1/payment-status` with the operator's API key
  before crediting — treating the callback itself as an untrusted hint
  per the upstream docs. New GET route at `/client-portal/webhooks/paylio`
  (the existing `POST /webhooks/{provider}` dispatcher is method-locked
  and can't accept GET).
- Config: `PAYLIO_API_KEY`, `PAYLIO_PAYOUT_ADDRESS`, optional
  `PAYLIO_CURRENCIES` (default `USD`), optional `PAYLIO_PROVIDER` to
  lock to a single upstream provider (`stripe`, `moonpay`, …) instead
  of the multi-acquirer router.
- Migration `044_paymentmethod_paylio`: adds `'PAYLIO'` (uppercase, for
  SQLAlchemy's `SQLEnum` serialisation) and `'paylio'` to the
  `paymentmethod` Postgres ENUM. Idempotent — `ADD VALUE IF NOT EXISTS`.

### Changed

- `update_apply.sh` smoke-check ceiling raised from 15 attempts (30s)
  to 60 attempts (120s), env-tunable via `SMOKE_MAX_ATTEMPTS`. The
  previous 30s window false-failed otherwise-healthy applies on small
  boxes (1 vCPU / 1 GB) where the full plugin set + online license
  validator routinely cold-starts in 70-90s, triggering unnecessary
  auto-rollbacks.
- Client portal `PaymentModal` now treats `paylio` as a card-style
  provider (single-currency, hosted-checkout flow) and surfaces the
  selected provider's display name in the "Pay by card" summary so
  single-provider portals don't leave the customer wondering who
  they're paying.

---

## v1.9.48 — 2026-06-01

Local post-update hooks + per-site landing analytics on the license server.

### Added

- **`/etc/vpnmanager-local-hooks/post-update.d/`** — operators with
  per-box customisations (overridden `client-portal-dist`, branded
  assets, custom nginx snippets that would otherwise be clobbered by
  each upstream tarball) can drop executable scripts there. They run
  in lexical order after a successful update, with `TARGET_VERSION`
  and `INSTALL_DIR` in the env. Hook failures log but don't roll back
  the update — the upstream code is already live; the hook's job is
  purely to overlay local overrides on top.
- **License server: per-site analytics.** `POST /api/visit`,
  `/api/heartbeat`, and `/api/copy-install` now accept an optional
  `site` field in the JSON body. Multiple landings (flirexa.biz,
  vpnsponge.xyz, future operators) can ping the same license server
  without merging into one bucket. Backward-compatible: missing /
  unknown `site` → "flirexa" (legacy file paths unchanged). The
  admin panel's Traffic page grows a per-site tab strip and a
  "Portal conversions" card with per-tier breakdown for non-flirexa
  sites.

---

## v1.9.47 — 2026-05-31

Security fix + activation-code support in `/api/license`.

### Fixed

- **`POST /api/v1/system/license` accepted any input as valid.** The
  guard `if info.type.value == "trial" and "Invalid" in
  info.validation_message` was always false because the
  `_create_free_license` fallback returns `type=FREE`, not `TRIAL`.
  Any string (including pasted activation codes, random text, blank
  input) returned `{"status": "activated"}` to the frontend, which
  then showed "License activated successfully!" even though no real
  key landed in `.env`. Now any input whose `validation_message`
  contains "Invalid" / "invalid", or that silently falls back to
  the FREE tier despite the user submitting a non-empty value, gets
  rejected with HTTP 400 and the actual error message.
- Same bug fixed in `/api/v1/system/license/replay`.

### Added

- **First-time activation via activation code.** `POST
  /api/v1/system/license` now branches on input shape: a 16-char
  alphanumeric string (with optional dashes) is treated as an
  activation code and round-tripped to the license server's
  `POST /api/activate` to exchange for a signed license key bound
  to this machine's hardware id. Full RSA-signed license keys
  still take the local-validation path as before. Customers can
  paste either form into the Settings → License field.

---

## v1.9.46 — 2026-05-31

Stale device-bind auto-release + customer-facing release endpoint.
Pair with the latest mobile build that surfaces a "Release this
device" button on `DEVICE_NOT_AUTHORIZED`.

### Added

- **`device_bound_at` + `device_last_seen_at` on `device_slots`.**
  Stamped when a slot first binds and bumped on every matched
  wg-quick fetch. Migration 043 adds both columns; existing rows
  start NULL and get filled on the next request.
- **Stale-bind auto-release.** If a mismatching device id arrives
  for a slot whose last_seen is older than 5 minutes, the slot
  silently rebinds to the new id instead of returning 403. Covers
  the recurring "force-close → reinstall → locked out" cycle where
  expo-secure-store regenerates the device UUID and the customer
  had no path to recover without operator intervention. A real
  concurrent second device bumps the heartbeat continuously, so
  the threshold doesn't open a hole for account-sharing.
- **`POST /client-portal/devices/{slot_id}/release`.** Owner-only
  endpoint that clears the bind so the next connect can claim the
  slot. The mobile app calls this from the new modal action button
  when it hits 403.

---

## v1.9.45 — 2026-05-31

Hotfix on top of v1.9.44 to drop a vendor host that leaked into the
open-core mirror.

### Fixed

- Inner installer no longer defaults `UPDATE_SERVER_BACKUP` to the
  operator's backup license-server host. The bootstrap selects and
  exports `UPDATE_SERVER` before invoking the inner, so the fallback
  was both dead code and a private-infra leak.

---

## v1.9.44 — 2026-05-31

Two follow-ups after live-testing v1.9.43 on a 1 GB / 1 vCPU clean
Ubuntu cloud image:

### Fixed

- **Outer and inner RAM thresholds were out of sync.** The bootstrap
  added just enough swap to hit 1024 MB then handed off to the inner
  installer's stricter 1500 MB gate, which immediately bailed. Outer
  now targets 1500 MB so both layers agree.
- **Inner RAM check now counts swap.** `effective_mb = total + swap`,
  so a 1 GB box with a 700 MB swapfile (the kind the outer creates
  automatically) is no longer treated as a hard fail.

### Added

- **`SB_SKIP_RAM_CHECK=1` escape hatch.** Power-users on weird memcg /
  container setups where `/proc/meminfo` underreports can bypass the
  inner RAM gate. Default-off; logged loudly when used so support
  knows we let it through deliberately.

---

## v1.9.43 — 2026-05-30

Adoption-funnel observability. The previous install funnel only emitted
`inner_start → silence` whenever an install died inside the main
installer script (every install on 2026-05-30 hit this, 100% silent
failure rate). We now know which phase actually dies.

### Added

- **Per-phase install telemetry.** `install.sh` now emits begin / ok /
  fail beacons around each major step (preflight, postgres, pip,
  alembic, systemd, etc) and registers an `EXIT` trap that reports
  `<phase>_died` if the script is killed mid-step (OOM, SIGHUP from
  `curl | bash` over a closed SSH session, network drop). The funnel
  endpoint now shows exactly where a failed install bounced.
- **RAM preflight (1500 MB minimum).** The installer used to OOM
  silently on 1 GB VPS instances while running `pip install`. Now we
  fail fast with a clear "resize to 2 GB" message and a dedicated
  `low_ram` beacon, so we know upfront which boxes can't actually run
  the panel.

### Changed

- `landing/install.sh` exports `UPDATE_SERVER`, `CHANNEL`, and
  `INSTALL_LOG` to the inner installer so it can beacon back to the
  same license server the bootstrap picked.
- Inner installer respects `INSTALL_TELEMETRY=off` for privacy
  opt-out, same as the bootstrap.

---

## v1.9.42 — 2026-05-30

Two small backend fixes that pair with the latest mobile / desktop
client release. Both relate to feedback received the same day.

### Fixed

- **`for_app_only` servers were hiding everywhere.** The detection
  helper expected the client app to send an `X-Client-App` header,
  but neither the mobile app nor the desktop client did — so every
  server marked app-only ended up invisible on both surfaces. The
  client app now sends the header on `/auth/login` and every
  authenticated request, so toggling a server "App-only" once again
  surfaces it on the app while hiding it from the web client portal
  and `/sub/{token}` URL.
- **Customers being logged out daily even with "Remember me".** The
  default `JWT_EXPIRATION_HOURS` was 24, which evicted any
  long-running app session at the same time each day. Default bumped
  to 90 days (2160 hours); operators can still override via env var.

### Notes

Bump the client app to a build that sends the `X-Client-App` header
when you ship this. Older app builds will still see the longer JWT
TTL but will not see `for_app_only` servers until they update.

---

## v1.9.41 — 2026-05-30

Stable cuts an arc of test-channel iterations (1.9.34 → 1.9.41) into
one promote. Highlights:

### Added

- **App-only servers (`for_app_only`).** New per-server toggle in the
  Servers menu hides the server from the web client portal and the
  public `/sub/{token}` URL while still exposing it to the official
  mobile and desktop client app. Detection by the `X-Client-App`
  header value or a matching user-agent prefix, so existing app
  builds pick it up without a client release. Cards get a small
  indigo "App-only" badge so the state is visible at a glance.
- **Auto-hide unreachable servers.** The health checker stamps a
  `last_good_health_at` timestamp on every successful poll;
  customer-facing endpoints (`/servers`, `/devices`, `/sub/{token}`)
  hide servers that haven't been healthy for 5 minutes. A new
  `force_visible` admin override pins a server visible regardless
  (amber "Pinned" badge). Servers that were never polled (just
  added) count as healthy until the first poll lands, so freshly
  added servers don't vanish before the first health pass.
- **Admin Slots page → bulk delete + browseable Add Slot.** Per-row
  delete + per-row checkbox + "select all slots of this user" shortcut
  + toolbar bulk delete. The "Add Device Slot" toolbar button (also
  available on the Users page) opens a modal that preloads the most
  recent 50 customers; typing filters via the existing portal-users
  search. Backend `DELETE /api/v1/clients/slots/admin/{id}` cascades
  through SlotManager so peers on every server get cleaned up.
- **Admin "Add Device Slot" on the Users page.** Old customers who
  paid for a plan but never figured out the portal's Add Device flow
  can be unblocked from `/portal-users/{id}` with one click. Enforces
  the same `max_devices` cap as the self-serve endpoint.
- **FCM push notifications (panel side).** New `fcm_tokens` table
  keyed by `(user_id, device_id)` matches the `X-Device-Id` slot
  bind. App registers via `POST /api/v1/client-portal/fcm/register`
  on every signed-in cold start; `DELETE` clears on explicit sign-out.
  `NotificationService.create_portal_notification` now best-effort
  dispatches via FCM in addition to writing the in-app inbox row.
  Sender uses the legacy `fcm.googleapis.com/fcm/send` endpoint with
  an admin-configured Server Key (Settings → Mobile push). Empty key
  → graceful no-op so the inbox keeps working without FCM credentials.
  Tokens that come back `NotRegistered` / `InvalidRegistration` are
  pruned automatically.
- **Bulk `POST /api/v1/client-portal/notifications/mark-all-read`**
  endpoint for the mobile and Windows clients.
- **Redesigned donate modal.** Two screens (info → amount picker),
  animated heart with ripple rings, $3/$5/$10/$25 presets + custom
  amount + 180-char comment, confetti success overlay. Localised in
  ru/en/de/fr/es. The "Support with $X" button currently plays the
  success animation only — payment integration (Stripe / Patreon /
  whatever) plugs in next.

### Changed

- `GET /client-portal/servers`, `GET /client-portal/devices`,
  `GET /sub/{token}` route every server through a unified visibility
  helper combining `customer_visible` × `for_app_only` × auto-hide
  threshold × `force_visible`.
- All PortalUsers prompts / confirms / alerts moved off hardcoded
  English to `useI18n().t()`. New strings added to ru/en/de/fr/es:
  ban-reason prompt, subscription cancel / reset traffic / delete
  user confirmations, payment confirm / reject / delete dialogs, and
  the broadcast "send to all X users" confirm with `{tier}`
  interpolation.

### Fixed

- **`update_apply.sh` now finds alembic in legacy venv layouts.**
  The script hard-coded `$INSTALL_DIR/venv/bin/alembic`, which broke
  on installs whose venv had stayed at the legacy `/opt/vpnmanager/venv`
  after the install-dir rename. Symptom: "Migration required but
  alembic not available" + exit 1 with no migrations applied. Adds
  a `find_alembic_bin` helper that searches `$ALEMBIC_BIN` override,
  `$INSTALL_DIR/venv/bin/alembic`, `/opt/vpnmanager/venv/bin/alembic`,
  `/opt/vpnmanager/venv/bin/alembic`, and the system PATH in order.
  The error log now enumerates every path checked so future operators
  can diagnose without grepping source.
- **`manager.py` prefers the staged release's `update_apply.sh` over
  the installed one.** When a buggy installed script would block its
  own replacement (e.g. the alembic-search bug above), the update API
  picks up the fixed script bundled in the new tarball as a way out
  of the bootstrap trap.
- 10 loguru calls in the new modules converted from `%`-style
  placeholders to `{}`-style (caught by the pre-publish lint;
  `%`-style format args silently drop through the stdlib→loguru
  bridge at runtime).

### Migrations

- `042_app_features_batch` adds `servers.for_app_only`,
  `servers.last_good_health_at`, `servers.force_visible`, and
  creates the `fcm_tokens` table with a `(user_id, device_id)`
  uniqueness constraint and indexes on both columns.

---

## v1.9.15 — 2026-05-21

### Changed

- **Dashboard "My Devices" — region picker on Download / QR for slot devices.** Before, every regional peer of a multi-region slot rendered as its own row with its own three action buttons; the section looked like the underlying DB, not like the customer's mental model of "one device." Slot peers now collapse to a single row (already shipped server-side in v1.9.8), and the per-row Download / QR buttons open a portal-styled region picker modal so the customer can choose a specific region or — only for Download — grab them all at once with a single click. The Delete trash icon already removes the whole slot in one shot (v1.9.9), so the device row now behaves as one logical object end-to-end. Legacy single-server peers (no `slot_id`) bypass the picker and run the action directly, same as before.

### Tooling

- **`fx-region-btn` design-token class** added next to the existing fx-modal styles. Used for the new picker, with success-tinted border for the active region and accent-tinted icon chip — mirrors the look of the device-slot server picker in `Devices.vue` so the experience feels continuous between the two pages.

---

## v1.9.14 — 2026-05-21

### Fixed

- **Logo on Login / Register would render broken the first time a tab was opened.** The fault was a race between Vue mounting and the async branding fetch, multiplied by the fact that `window.__branding` is plain JS — not reactive — so the `brandLogo` computed evaluated once on first read and cached forever. Depending on which raced first, the customer saw either the working bundled platform asset or whatever path `branding_logo_url` pointed at, and on at least one host that path no longer existed (the FastAPI catch-all returned `index.html` as `image/png`). Refresh-once-then-broken-again was the diagnostic clue. Resolved by pre-fetching `/api/v1/public/branding` in `main.js` *before* `app.mount()`, so every component's first read of `window.__branding` already has the real values. Adds a small (≤2.5s timeout) blocking step to first paint; falls back to empty branding on failure, which is exactly the fresh-install default.

### Changed

- **Bundled platform asset** (`flirexa-logo.png`) is what every brand-aware component falls back to when no operator branding is loaded — confirmed working from both the customer portal (`/`, `/assets/…`) and any host serving the SPA. Operators who had `branding_logo_url` pointing at a moved legacy path (`/static/…` on this build serves `index.html`) should update the value to `/flirexa-logo.png` (or upload a fresh logo through the admin panel). Existing customers on the fix above won't see broken images regardless, since the brand pre-fetch is no longer racey.

---

---

## v1.9.13 — 2026-05-21

### Changed

- **Region-switch rate limit is now a token bucket** instead of the fixed 30s post-switch cooldown. Each `DeviceSlot` carries 5 tokens that refill at one token every 6 seconds (configurable via `SLOT_SWITCH_BUCKET_SIZE` / `SLOT_SWITCH_REFILL_SECONDS_PER_TOKEN`). Each switch consumes one token; an empty bucket replies 429 with a "wait Ns" hint that's still parseable by the existing portal countdown chip. The fixed cooldown blocked legitimate burst-testing (a customer trying three regions in a row to find the closest) just as hard as a click-spammer; the bucket lets the burst go through and only throttles sustained spam.

### Fixed

- **Login / Register: default flirexa logo lost its blue accent frame** on installs where the operator left `branding_logo_url` pointing at the platform default. The bare-mode toggle was triggering on ANY non-empty logo URL, including the admin-side platform field, which made fresh installs look unfinished. Bare mode is now only triggered when the operator explicitly uploaded a *customer-facing* logo (`branding_customer_logo_url`); the platform logo keeps its gradient chip.
- **RTT chip alignment on the device-slot region picker.** Pills used `inline-block` with 1px vertical padding and no `line-height`, leaving the number baseline-aligned against the neighbouring "Active / Standby" badge and the IP address — they looked off-center. Now `inline-flex` with `align-items: center`, fixed 18px height, `line-height: 1`, and a `min-width: 44px` so the chips render the same size whether they hold "12 ms" or "184 ms".

### Migration

- `038_slot_switch_token_bucket` adds `device_slots.switch_tokens FLOAT NOT NULL DEFAULT 5.0`. Existing slots start with a full bucket on first read after the upgrade — no surprise 429s right after deploy.

---

---

## v1.9.11 — 2026-05-21

This release rolls 1.9.9 + 1.9.10 + 1.9.11 into one stable promote — the test-channel intermediates either had narrow scope or shipped a feature we walked back before stable.

### Added

- **Browser-side latency probe on the device-slot region picker.** `GET /client-portal/servers/<id>/probe` proxies a fetch to each node agent's `/health` (since browser mixed-content rules block HTTPS portal → HTTP node fetches) and reports the RTT. The Devices page lights up each server card with a colour-coded chip — green ≤60 ms, amber ≤180 ms, red above — and tags the lowest-RTT server "Fastest". The number is portal→server, not user→server, so it's a relative health/closeness signal rather than ground truth for the customer; the auto-sync logic below is what compensates when the customer's actual routing differs.
- **Auto-sync of the active-region flag from real handshakes.** If the customer flipped tunnels in their VPN app without clicking on the portal, the freshest handshake among the slot's peers reveals where traffic is actually flowing. `SlotManager.auto_sync_active_from_handshake` follows that handshake — flipping `enabled`, calling `disable_client` / `enable_client` on the previously-active region — so the panel indicator stops drifting from reality. Manual switches still win because of a 30-second post-switch cooldown inside the helper.
- **`FxHelp` tooltip component** (`?` chip with a styled popover) for inline explanations next to feature titles. Wired up on the device-slot region picker title and the manual config-download section title in `Devices.vue`, with EN + RU copy explaining what the feature does and what the user is expected to do.
- **Per-slot subscription-URL backend endpoint** (`GET /client-portal/sub/<token>/slot/<slot_id>`) that always returns the currently-active region's config for that one slot. Designed for VPN clients that support subscription-mode polling (WG Tunnel on Android, AmneziaVPN with scheduled updates, Hiddify, etc.). **No UI surface in this release** — most mainstream WG clients don't poll subscription URLs, so the "switch on portal, app auto-updates" promise was misleading for the average customer; the endpoint stays available for advanced users / a future custom mobile client. Will be reintroduced in the UI together with a native app.

### Fixed

- **Password-verify bypass when deleting a device.** The customer-side delete flow re-uses `POST /auth/login` to check the user's password, then proceeds to `deleteDevice` / `deleteSlot`. The `try { login(...) } catch (verifyErr)` blocks only short-circuited on HTTP 400/401, leaving every other failure mode (network blip, 5xx, 429, CORS) to fall through to the actual deletion without the password being verified. Both `Devices.vue` and `Dashboard.vue` now treat anything non-2xx as a failed verification, surface the error to the customer, and return without touching the slot/peer.
- **Wrong password on device-delete logged the customer out of their session.** The verify-only login above hit 401 on a wrong password, which tripped the global axios 401 interceptor and wiped the access token / forced a redirect to /login. The login API now accepts a per-request `_skipAuthInterceptor` flag and the delete-flow passes it, so a typo at the password prompt produces an inline error instead of an unrequested sign-out.
- **`/wireguard/clients` was returning per-server peers without their `slot_id`** because `slot_id` lives on the `ClientUserClients` link row, not on `Client` itself, and the admin-API round-trip dropped it. The Dashboard's `displayDevices` reducer relied on that field to collapse a multi-region slot to one row; without it, every peer landed in the "standalone" bucket and a 5-device subscription would render 10+ rows. The portal endpoint now joins the link table and attaches `slot_id` per client.
- **`devices_used` mis-counted slot peers as separate devices** (the "My Devices 2/1" bug). The subscription endpoint summed `ClientUserClients` rows instead of using the same slot + legacy union the slot/peer-create limit checks already use. The "X / N" display everywhere on the dashboard now matches what the cap actually enforces.
- **Deleting a slot-backed device from the Dashboard removed only the active region's peer.** The dashboard delete path called `DELETE /wireguard/clients/<id>` whether the row belonged to a slot or a standalone peer, leaving the other regional peers of the slot orphaned in the DB. When the deleted row has a `slot_id`, the dashboard now routes to `DELETE /devices/<slot_id>` so every regional peer of that slot is removed together. Legacy single-server peers fall back to the per-peer endpoint.
- **Device-slot create / delete modal in `Devices.vue` rendered unstyled.** The modal markup used `fx-modal` / `fx-modal-head` / `fx-modal-foot` class names; `design-tokens.css` defines them as `fx-modal-box` / `fx-modal-header` / `fx-modal-footer`. The mismatch meant the modal overlay rendered but the inner card lost its border, padding, and footer divider. Class names now match the design system.
- **Notification bell dot lit up for already-read items.** `Layout.vue` derived its unread count from `notifications.value.length`, but `GET /notifications` returns every notification, not just unread ones. The badge now filters by `is_read === false` (with a fallback to `.read` for older payload shapes).
- **Payment modal "Expires in X minutes" was frozen at the value it was opened with.** The `expiryMinutes` computed called `new Date()` directly without a reactive dependency, so a customer staring at the modal would see a static countdown that never decremented. A ticking `now` ref (15-second interval, cleared on unmount) drives it now.
- **"Next charge" amount in Billing showed even when no charge was scheduled.** With `auto_renew=false` or `status=cancelled`, the row still displayed `$X.XX` — misleading customers into thinking they'd be billed again. It now reads "—" / "No upcoming charge — auto-renew is off" when there is no charge actually due.
- **Auto-renew toggle didn't lock during the request.** A rapid double-click could send two opposite-direction toggles back-to-back and leave the UI out of sync with the backend. The input is now disabled and shows a small spinner while a request is in flight.
- **Cooldown countdown after switching slot regions** is wired now. The backend already returned `Please wait Ns before switching servers again.` on 429; the frontend ignored the seconds, the customer hit the same button again, got the same error, and assumed the panel was broken. The Devices page now parses the seconds out of the 429 response, runs a one-second-tick countdown chip under the server picker, and clears it when the cooldown expires.

### Changed

- **Confirm / dialog UX:** every destructive action that used `window.confirm()` (subscription cancel, etc.) now opens an `fx-modal-box`-styled confirmation matching the rest of the portal — same shell, same buttons, same dark-mode treatment. Escape closes any open modal (added a `useEscapeClose` composable that attaches a `keydown` listener only while the relevant ref is true and tears it down on close / unmount).
- **Login / Register: drop the blue accent frame when the operator uploaded a custom logo** (already in 1.9.7, kept here for visibility). The 56×56 gradient chip was meant for the bundled platform glyph; squashing a customer-branded wordmark into a 32×32 area inside the chip produced an unreadable thumbnail. The frame now only renders for the default bundled logo; custom logos render at native proportions (capped at 200×88 on desktop, 160×72 on mobile).
- **`get_current_version()` resolves the VERSION-file path on every call** instead of pinning it at module import (1.9.7 — kept here because some installs still hit the stale-path "0.0.0 / requires 1.0.0" loop after a rolling deploy). The resolver walks `$VERSION_FILE` env → `<install>/current/VERSION` → `<install>/VERSION` → highest semver in `<install>/releases/` → last-resort `0.0.0`.

### Removed

- **"Smart Subscription Link" UI section** (briefly visible on test-channel 1.9.10). The promise — paste this URL into your WireGuard / AmneziaWG app and switching regions on the portal updates the app automatically — only holds in clients that poll subscription URLs (WG Tunnel, Hiddify, AmneziaVPN with scheduled updates). The official WireGuard apps for Android / iOS don't, so most customers would have ended up with a URL that worked exactly once as a config import and then never updated, which is worse than just downloading a `.conf`. The backend endpoint stays for advanced use; the customer-facing surface is parked until we ship a native client app that can use it properly.

### Tooling

- **`useEscapeClose` composable** under `src/web/client-portal/src/composables/`. Wires Escape to any modal-state ref; attaches `keydown` only while open; cleans up on unmount.
- **`fx-spin` utility class** on `design-tokens.css` for inline icon-based loading indicators. Used by the auto-renew toggle, the cancel-subscription button, and the Add-device button when an action is in flight.

---

## v1.9.8 — 2026-05-20

### Fixed

- **Dashboard "My Devices" list was rendering one row per regional peer** instead of one row per Device Slot. A 5-device subscription with two multi-region slots would balloon to 10+ entries, half of them disabled per-region peers the user didn't directly create. The Dashboard already had slot-aware deduplication client-side (added in v1.9.7), but `/client-portal/wireguard/clients` wasn't returning `slot_id` on each peer — it's stored on the `ClientUserClients` link row, not on `Client` itself, so the admin-API roundtrip dropped it and every peer ended up in the "standalone" bucket of the frontend's `displayDevices` reducer. The portal endpoint now joins the link table and attaches `slot_id` per client; the dashboard collapses peers to one row per slot (preferring the live-handshake peer, then any enabled peer). Legacy single-server peers (no `slot_id`) still render as individual rows.

---

## v1.9.7 — 2026-05-20

### Fixed

- **`get_current_version()` now resolves the VERSION-file path on each call** instead of pinning it at module import. The old behaviour froze the path before the `current/` symlink existed in some apply flows, leaving the panel reading a non-existent file forever and reporting current version as `0.0.0`. With the current version stuck at `0.0.0`, every checked manifest came back as `Update X.Y.Z requires minimum version 1.0.0, current is 0.0.0` and updates couldn't be applied. The resolver now walks: `$VERSION_FILE` env override → `<install>/current/VERSION` → `<install>/VERSION` → highest semver directory inside `<install>/releases/` → only then `0.0.0`. Existing installs whose VERSION file vanished or whose `current/` link rotated will self-recover at the next status poll.
- **Counting one slot device as N peers on the Dashboard** ("My Devices 2/1"). A Device Slot with peers provisioned on two regions was inflating the device-used counter by 2× because the subscription endpoint summed `ClientUserClients` rows rather than slots. `devices_used` in `/client-portal/subscription` now uses the same slot+legacy union the create-slot limit check already used, so the dashboard "X/N" matches what the cap actually enforces. The "My Devices" panel also collapses per-region peers down to one row per slot, preferring the live-handshake peer for the visible region.
- **Missing i18n keys in the client portal.** `common.refresh`, `dash.overDeviceLimit`, `dash.overDeviceLimitHint`, `dash.manageDevices`, `devices.atLimitHint` and the new delete-confirmation strings were rendering as their literal key names because vue-i18n's `$t(missing) || 'fallback'` pattern doesn't fall back — it returns the key name as a truthy string. Translations now ship in EN + RU and the precedence-trap fallback is gone.

### Changed

- **Login / Register: drop the blue accent frame when the operator uploaded a custom logo.** The 56×56 gradient chip was meant for the bundled platform glyph; squashing a customer-branded logo (often a wordmark or wide logotype) into a 32×32 area inside the chip produced an unreadable thumbnail. The frame now only renders for the default bundled logo. When `branding_customer_logo_url` or `branding_logo_url` is set, the logo renders bare at its native proportions (capped at 200×88 on desktop, 160×72 on mobile).
- **Over-device-limit notice on the Dashboard is now styled as a proper portal card** (accent-tinted gradient background, warning border-left strip, icon chip, primary "Upgrade plan" + ghost "Manage devices" actions) instead of the older inline warning band that didn't match the rest of the portal aesthetic. Same card shape ships in `Devices.vue` for the at-slot-limit notice — both pages feel consistent now.

### Added

- **Password-confirm before customer-side device delete.** A misplaced tap on the trash icon used to wipe a working VPN config behind a single `confirm()` dialog. Now a modal asks the user to re-enter their account password before the deletion goes through; the verification reuses the existing `/auth/login` flow (stateless JWT means the fresh token is discarded harmlessly) so we don't have to ship a new endpoint. The admin keeps an unprompted delete path from the panel for legitimate cleanup. Applied to both the Dashboard quick-list and the dedicated `Devices.vue` slot cards.

---

## v1.9.5 — 2026-05-20

### Added

- **Separate customer-facing logo field** — `branding_customer_logo_url`. Set it when you want a different logo in the client portal than in the admin panel (most common case: keep the platform mark on the admin side, use your own brand in the portal). Empty → falls back to the shared `branding_logo_url`, then to the bundled platform default. New "Customer-facing logo" upload row in Settings → Branding with its own remove button.
- **Logo-only customer header.** If `branding_customer_app_name` is empty, the client portal header now renders only the logo — useful when the logo image already contains the brand wordmark and showing it again as text would be redundant. The footer copyright degrades gracefully too (`© 2026` instead of `© 2026 ` with a dangling space).

### Fixed

- **i18n for new Settings fields.** The "Customer-facing brand name" field added in v1.9.2 didn't have translations registered, so the label rendered as the literal i18n key (`settings.customerAppName`). Same for the hint underneath. Translations now ship in EN + RU; the inline `||` fallback pattern (which doesn't actually work in vue-i18n) is gone.
- **App-mount title only uses customer name.** `App.vue`'s `onMounted` used to write `document.title = branding_customer_app_name || branding_app_name`. When the operator deliberately cleared the customer name (logo-only mode), the admin-side `branding_app_name` would leak into the customer's browser tab. The fallback is dropped — only the explicit customer name moves the title; otherwise leave the server-rendered "VPN" default in place.

### Tooling

- **Upload endpoint accepts `target`** query parameter (`logo` | `customer_logo` | `favicon`). Same persistent `/uploads/` storage, different `SystemConfig` row gets the resulting URL. Frontend uses this for the new customer-logo uploader.

---

## v1.9.4 — 2026-05-20

### Fixed

- **Branding assets survive release swaps now.** The logo-upload endpoint (`POST /system/branding/logo`) used to write files into `src/web/static/`, which sits inside the release tree (`/opt/vpnmanager/releases/<ver>/src/web/static/`) that the `current` symlink points at. Each release swap replaced that directory, silently dropping every branded logo and reverting `branding_logo_url` paths to 404. Uploads now land in `$INSTALL_DIR/data/uploads/` — outside the release tree, persisted across upgrades — and the URL stored in `SystemConfig` is `/uploads/<name>` instead of `/static/<name>`. The legacy `/static/` mount stays in place so old branding URLs keep working for existing installs.
- **Customer-portal logo no longer cross-origins to the admin host.** The client-portal frontend used to build logo URLs as `https://<host>:10086/static/<name>` regardless of how the portal itself was reached. When nginx fronts the portal on 443, that admin-port URL either hit a different TLS cert (cert mismatch) or 404'd outright, and the customer saw a broken-image icon next to "Acme VPN". The portal now mounts `/uploads/` and `/static/` itself, and the frontend leaves path-style logo URLs alone — same-origin fetch, no cert juggling, no 404.

### Added

- **`/uploads/` static mount** in both admin API and client portal. Backed by `$INSTALL_DIR/data/uploads/`, served same-origin from whichever host is requesting it.

---

## v1.9.3 — 2026-05-20

### Fixed

- **Customer portal couldn't load branding when fronted by nginx on 443.** `App.vue` fetches `/api/v1/public/branding` on mount to populate `window.__branding`. That endpoint was only registered on the admin API process (port 10087). When `window.location.port === '10090'` the frontend correctly cross-origin'd to the admin host:port, but when the portal sits behind nginx on the customer-facing main port the request stays on the same origin — and the catch-all SPA route in `client_portal_main` answered with `index.html` (HTTP 200). Axios then tried to parse the HTML as JSON, silently failed, left `window.__branding` undefined, and the portal rendered the bundled platform logo + "VPN" fallback for the brand name. The branding endpoint is now also registered inside `client_portal_main`, reading the same `SystemConfig` rows via `get_all_branding()`, so any host serving the portal exposes the field at the path the frontend already expects.

---

## v1.9.2 — 2026-05-20

### Added

- **`branding_customer_app_name` field — separate admin / customer-facing brand names.** Operators can now keep their admin panel labelled with the platform name (e.g. "Flirexa") while customers see only the operator's own consumer brand (e.g. "Acme VPN", "Acme VPN"). The new field appears in Settings → Branding with placeholder "Acme VPN" and a help hint. Falls back through customer name → admin app name → "VPN" so unfilled installs keep their old display.

### Changed

- **Client portal title / iOS app meta / PWA manifest now reflect customer brand at serve time.** The portal backend reads the branding config when handing out `index.html` and `manifest.json`, rewriting the `<title>`, `apple-mobile-web-app-title` meta, and the PWA `name` / `short_name` fields to the customer-facing brand. Previously these were baked into the static build at "Flirexa" and could only be patched by document.title-after-mount JavaScript (which caught the tab label but not the social-share preview or the iOS home-screen install name).
- **Branding fallbacks across the portal frontend dropped "Flirexa" defaults.** Header, Login, Register screens, and Support page now fall back to a neutral string instead of leaking the platform default to operator customers. Support page email / docs / status URLs default to empty so they hide entirely when the operator hasn't filled in their own — no more "support@flirexa.biz" on third-party portals.
- **Email-template fallbacks** (welcome / verification / payment / expiry) follow the same chain: customer name → admin app name → "VPN".

---

## v1.9.1 — 2026-05-20

### Fixed

- **Device Slots admin tab showed raw i18n keys instead of localised strings.** The `slots.*` translation block was never defined, and the inline `$t('slots.X') || 'fallback'` pattern doesn't work in vue-i18n — when a key is missing, `$t()` returns the key name itself (a truthy string), so the `||` branch never triggers. Both EN and RU locales now ship the full `slots.*` block (titles, column headers, peer detail labels, totals) plus `common.expand` / `common.collapse` for the row toggle. The broken fallback pattern is dropped from the template — clean `$t('slots.…')` calls throughout.

---

## v1.9.0 — 2026-05-20

### Added

- **Admin "Device Slots" tab.** New sidebar entry between Clients and Servers. One row per slot showing the customer, label, active region, total traffic across all regions, and an expandable per-peer view (server, IPv4, enabled/disabled, last handshake, RX/TX). Aggregated server-side via a new `GET /api/clients/slots/admin` endpoint that bulk-loads peers/users/servers and reuses the existing `_enrich_handshakes` helper so the live status matches the Clients page exactly.
- **Email notifications for subscription lifecycle.** Two new templates in `EmailService`:
  - `send_expiry_warning_email` — fires from the scheduler at the 7-day / 3-day / 1-day marks alongside the existing Telegram / portal-push notifications. EN + RU copy with portal CTA.
  - `send_payment_received_email` — fires from `subscription_manager.complete_payment` right after the existing payment-confirmed notification. Includes amount, currency, plan, new expiry date, portal CTA. EN + RU.
  Both paths are best-effort: SMTP misconfigured / user has no email / template error all silently no-op so the underlying notification flow never breaks.

### Changed

- **Slot peer names are now label-based instead of `slot-{id}`.** The old name (`slot-9-TexasUSA` → `slot-10-TexasUSA` after a recreate) leaked the auto-increment of `device_slots.id`, which is fine in a DB but reads as "wat" in the admin Clients list. Names now combine the customer's chosen device label (sanitised to `[A-Za-z0-9._-]`) with a 4-character SHA-256 suffix of the slot's shared public key and the server name. Stable across recreate-with-same-label-and-keypair, disambiguates two same-labelled slots via the key-derived suffix.

### Tooling (no runtime impact for installs)

- **pytest suite for the slot system.** 24 tests covering peer-name shape, free-tier toggle (truthy/falsy variants), slot creation (one peer per visible server, shared keypair, exactly one enabled), bare-address storage convention, `heal_slot` idempotency, backfill onto a newly-added server, hidden-server skip. Run in 1.2s against in-memory SQLite + a mocked WireGuard adapter.
- **GitHub Actions workflow** (`.github/workflows/tests.yml`) — runs the logger-style linter, the migration linter scoped since the last release tag, and the full pytest suite on every push to master and every PR. Catches the family of regressions that previously only surfaced on a customer's production DB.

---

## v1.7.10 — 2026-05-19

### Changed

- **Client portal Dashboard "Add Device" buttons now route to the Devices page** instead of opening the legacy single-server create modal. Three entry points in the Dashboard (status-banner CTA, Quick Actions card, My Devices header) all become `router-link` → `/devices`. Existing legacy single-server peers continue to display in My Devices as before, but creation of new devices funnels through the slot-based Devices page only. This removes the source of the "3 configs from one device" confusion — when both the Dashboard and the Devices page each had their own creation path, a user could end up with one legacy peer + one slot for a `max_devices=1` plan because the two endpoints didn't count each other's output.

---

## v1.7.9 — 2026-05-19

### Added

- **Device slots auto-extend when a new server is added.** Until this release, slots froze their region set at creation time — customers who already had a device couldn't get a peer on a freshly-added server without deleting and recreating their slot. Now any of the following events fan a peer for every existing slot onto the new server with the slot's shared keypair:
  - Creating a server with `customer_visible=true`
  - Flipping `customer_visible` from false to true on an existing server (the reverse flip is intentionally non-destructive: existing slot peers stay so currently-connected customers don't drop mid-session)
  - First open of `/client-portal/devices` after any of the above (lazy-heal fallback for misses, e.g. server added before this release shipped)

- **`SlotManager.provision_slot_on_server(slot, server)`** and **`SlotManager.heal_slot(slot)`** as the building blocks. Both are idempotent — calling on an already-provisioned slot is a no-op — and pool-exhaustion / node-down failures on one server don't block the others. New peers are inserted dormant (`enabled=False`) so the slot's currently-active region stays the only one accepting handshakes; the customer just sees the new region appear in their server picker.

### Behaviour

- New peers inherit the bandwidth / traffic / expiry caps from existing peers in the same slot, so a slot created on a paid tier doesn't get an uncapped peer when a region is added later.
- Proxy servers (Hysteria2 / TUIC) are skipped — they don't fit the slot model.
- Backfill is best-effort: a server with a full IP pool logs a warning and continues with the next slot, rather than aborting the rest of the fan-out.

---

## v1.7.8 — 2026-05-19

### Fixed

- **Admin "Online Users" tab false-flagged slot peers across regions as online.** `_enrich_handshakes` built a global `{pubkey → last_handshake}` map and then assigned the timestamp to every `Client` row whose pubkey matched. That's fine for legacy single-server peers, but device-slot peers intentionally share one keypair across every region — so a live handshake on the Texas peer was being applied to the Cali Client row too, and the panel reported both regions online while only one was actually carrying traffic. Same false positive surfaced anywhere consuming `Client.last_handshake` (the Clients page handshake column, the map-data endpoint, the client-portal `online` flag). The map is now keyed by `(server_id, pubkey)`, so each server's handshakes stay scoped to its own Client rows.

---

## v1.7.7 — 2026-05-19

### Fixed

- **AmneziaWG / WireGuard mobile rejected long device-slot config filenames.** The client portal's per-region download wrote files as `{slot.label}-{server.name}.conf` (e.g. `phone-TexasUSA-AWG-Residential.conf`, 29 chars). On import, the mobile app maps the filename to a Linux TUN interface name, which is capped at 15 characters by the kernel — anything longer fails with "invalid profile". The download filename now uses just the server's display name, sanitised and truncated to 15 chars, dropping the label prefix entirely. The slot label is still shown in the portal UI; only the on-disk filename was the problem.

---

## v1.7.6 — 2026-05-19

Three fixes for the device-slot system caught by an operator testing multi-server toggling against a production panel.

### Fixed

- **`Address = X/32/32` in client `.conf`.** The `clients.ipv4` column has always stored bare addresses ("10.66.66.5") by convention, and every consumer adds the `/32` suffix at read time. A recent refactor of `ClientManager.create_client` and the new `SlotManager.create_slot` started writing `"10.66.66.5/32"` into the column, so the existing `f"{client.ipv4}/32"` callsites doubled up to `"10.66.66.5/32/32"`. AmneziaWG / WireGuard mobile apps reject that as malformed. Restored the bare-address convention in both writers, and the `wg add_peer` calls that needed CIDR form now apply the suffix themselves. Same fix applied to `ipv6` / `/128`.
- **Region toggle didn't actually disable the old peer on the node.** `SlotManager.switch_active_server` pre-flipped `client.enabled = False` in the session before calling `core.disable_client(client.id)`. `ClientManager.disable_client` re-reads the same session object, sees `enabled=False`, treats the peer as "already disabled" and short-circuits — skipping the `wg remove_peer` call. The peer stayed live on the interface even though the panel reported DISABLED, so customers could keep handshaking against a region they'd toggled off. Removed the pre-flip; `enable_client` / `disable_client` now drive both the DB flag and the wg-set call themselves.
- **Subscription device-count double-counted across slot and legacy paths.** Adding a device via the Dashboard "Quick Actions" went through `/wireguard/create` (legacy single-server peer), adding via the Devices page went through `/devices` (multi-region slot), and the two endpoints applied the cap differently — legacy counted every `ClientUserClients` row including each slot's per-region peers (so one slot inflated the count by N), while `/devices` counted only `device_slots`. A subscriber could therefore create one slot AND one legacy peer with a `max_devices=1` plan. Both endpoints now count uniformly: `slot_count + legacy_count`, where each slot is one device unit regardless of how many regions it fans across.

---

## v1.7.4 — 2026-05-19

### Changed

- **Default subnet for new servers bumped from `/22` to `/19`.** A `/19` gives 8190 usable hosts, enough room for thousands of slots fanning across multiple regions without exhausting the pool. Operators on the older `/22` or legacy `/24` defaults are not touched — this only sets the value for fresh server rows that don't override it. The same release bumps `Server.max_clients` default from `1000` to `8000` to match. The IP allocator added in 1.7.0 already handles arbitrary prefix lengths, so there's no schema change required.

---

## v1.7.3 — 2026-05-19

Hotfix release with three independently shippable fixes for the 1.7 series.

### Fixed

- **Client portal `/devices` returned 500.** `list_device_slots` referenced the `Client` ORM model but the module's other functions import it locally per-function, so the name wasn't in scope when the device-listing endpoint ran. The endpoint NameError'd, the portal showed an empty Devices page, the customer clicked "Add device" anyway, and the create endpoint correctly answered 409 device_limit_reached because the slot was actually already there. Added the local import.
- **`update_apply.sh` reported "VERSION mismatch after update" on every successful rollback.** When a failed apply rolled back to the previous release, the smoke-check reread VERSION from `effective_runtime_root()`, which still pointed at the failed-and-now-stranded target release dir. That dir's VERSION file said 1.7.1 while the `current/` symlink had already been restored to 1.6.37, so the check reported a spurious mismatch and exit-code'd 1 on a rollback that had actually succeeded. The rollback path now forces `ROLLBACK=1` into the smoke-check so it reads VERSION through the restored symlink instead.

### Tooling

- **`push_test.sh` now auto-detects DB migrations** in `alembic/versions/` since the last shipped tag and passes `--migrations` to `publish_update.py` automatically. Forgetting the manual flag is what broke the 1.7.1 rollout — every stable customer's auto-apply tried to migrate inside the API/worker lifespan hooks instead of pre-swap, the two processes raced each other, and the post-update health check rolled the upgrade back.
- **New `tools/lint_migrations.py`** runs from `push_test.sh` against migrations changed since the last tag. Catches the PG-only family of bugs that fresh-install test VMs don't surface: `drop_index` on a UNIQUE-backed column (the 037 bug), `AUTOCOMMIT` isolation combined with `ALTER TYPE ADD VALUE` (the 034 bug from 1.6.24), and unguarded `drop_column`/`drop_table` calls without an `inspect()` probe.
- **`push_all.sh` now also tags the private mirror.** Previously only the public mirror got `v1.7.x` tags, so `git describe --tags` from the local checkout returned an ancient `v1.4.61` baseline and the linter walked through all historical migrations every run.

---

## v1.7.1 — 2026-05-19

Two themes in this release: a new multi-server "device slot" model that lets one VPN device roam between regions, and a fix for an installer false-alarm that was scaring guests off mid-install.

### Added

- **Device slots (multi-server toggle).** A device slot owns one shared keypair plus a peer record on every customer-visible server. The client portal shows one device card per slot with a server picker; flipping it enables the peer on the new region and disables the previous one, server-side. The user's VPN app keeps using the same config — no re-import, no rekey. Subscription `max_devices` bounds slot count, not per-region peers, so a 1-device plan can roam between US/EU/Asia/AU/CA without "using" extra slots. Anti-abuse is built in: leaking the config bundle doesn't grant extra access because only the active region's peer accepts handshakes.
  - New table `device_slots`, new FK `client_user_clients.slot_id` (nullable — legacy single-server devices keep working unchanged).
  - New endpoints: `GET/POST/PATCH/DELETE /client-portal/devices`, `POST /client-portal/devices/{id}/switch-server`, `GET /client-portal/devices/{id}/config/{server_id}`.
  - 30-second cooldown between regional switches per slot (env `SLOT_SWITCH_COOLDOWN_SECONDS`).
  - New client portal page at `/devices` — server grid, inline rename, per-region download buttons, add/remove device.
- **`/22` is the new default subnet for newly-created servers.** The historic `/24` default with `max_clients=250` ran out of host space quickly once you fan a slot across 5 regions. New default: `address_pool_ipv4=10.66.0.0/22`, `max_clients=1000`. Existing servers untouched — only fresh inserts get the new default.

### Fixed

- **Installer `/dev/tty: No such device or address` warning under `curl … | bash`.** When no controlling terminal is attached (the typical SSH-over-pipe install), bash printed `install.sh: line 1095: /dev/tty: No such device or address` to stderr at the License Activation prompt and silently fell through to FREE tier. The error was harmless — the install completed — but guests reasonably mistook the bash error message for a fatal failure and re-ran the installer 4 times in a row. Now the script opens `/dev/tty` via `exec 9<…` with stderr suppressed, so the only thing the no-pty path emits is a clean `No TTY available — installing in FREE tier` log line.
- **IP allocator now handles arbitrary CIDR prefixes.** The previous allocator hard-coded the last octet (`{base}.{ip_index}`) and only scanned `2..255`, silently capping any pool larger than `/24`. Replaced with `ipaddress.IPv4Network`-based math that walks the actual host range, so a `/22` cleanly yields offsets 2 through 1021.

### Schema

- `Client.public_key` is no longer standalone-unique. Replaced with a composite partial unique on `(public_key, server_id)` — required for slot-shared keys to live on multiple servers. Proxy clients (NULL public_key) are unaffected by the partial predicate.

---

## v1.6.37 — 2026-05-19

Client-portal connection indicator now reflects actual VPN state.

### Fixed

- **Status orb stayed green even with VPN disconnected.** The portal's connection badge and the dashboard's status orb were both wired to `device.enabled`, which is just the admin-side enable flag — it stays true after the user turns off WireGuard in their app, so the indicator looked permanently online. The orb now lights green only when a device has a fresh WG handshake (within ~3 minutes); otherwise it shows "Ready — not connected" with a neutral colour. Same fix on the per-device badge: three states (Connected / Ready / Disconnected) instead of the old two.

### Added

- `online: bool` and `last_handshake: str|null` fields on the internal `/clients/by-ids` response, computed by reusing the same `_enrich_handshakes` helper the admin Clients tab already uses. Operators with custom portals can read `online` directly instead of re-implementing handshake freshness logic.
- New i18n strings (`dash.deviceReady`, `dash.statusReady`) in all five portal locales (en / ru / de / fr / es) for the third connection state.

---

## v1.6.36 — 2026-05-19

Installer hardening release. The bootstrap and main `install.sh` now produce useful diagnostic output when something goes wrong, and the bootstrap auto-creates swap on memory-starved VPS images instead of dying silently to the OOM killer.

### Fixed

- **`systemctl start vpnmanager-api` failures now print the reason.** Previously `set -euo pipefail` at the top of the installer caused the script to abort on a failed service start without showing why — leaving the operator to re-run the whole installer 3-4 times hoping it would clear up. The installer now catches the failure and dumps the last 15 lines of `systemctl status vpnmanager-api` plus the last 30 lines of `journalctl -u vpnmanager-api`, then a one-line hint about common causes (port 10086 already bound, half-applied alembic migration from a previous attempt, broken Python import). Fail-on-first-try with a real error message instead of silent retries.
- **Full pip-install log preserved on failure.** Wheel build errors (the `cryptography` / `psycopg2` / `lxml` family on stripped VPS images) almost always have the real `Error: …` line ~30 lines above the tail. The old `2>&1 | tail -5` swallowed that root cause. The full pip output now streams to `/tmp/vpnmanager-pip-install.log` and the installer prints `tail -40` on failure (plus the log path so operators can grab the whole thing).

### Changed

- **Bootstrap `install.sh` minimum memory raised to 1 GB (RAM + swap combined).** The old 512 MB floor lied: `pip install cryptography` peaks at ~700-800 MB during wheel compilation and OOM-killed pip on 512 MB images, leaving the installer to die on the second retry too. When `RAM + swap < 1024 MB`, the bootstrap now provisions a swap file at `/swapfile-vpnmanager` sized to bring the total to 1.25 GB, persists it via `/etc/fstab`, and continues. Cheap 512 MB VPS targets now install cleanly without manual swap setup.

---

## v1.6.35 — 2026-05-19

Follow-up to v1.6.34: the **Free tier** admin setting only had English strings, so non-English operators saw the i18n key name (`settings.freeTierToggle`) instead of a translated label.

### Fixed

- Translations for `settings.freeTierTitle`, `settings.freeTierHint` and `settings.freeTierToggle` added to all five admin locales (en / ru / de / fr / es). The inline `$t(key) || 'English fallback'` pattern used in v1.6.34 doesn't work the way it looks: vue-i18n returns the *key name* (not an empty string) when a translation is missing, so the `||` fallback never triggered. The fix is to ship the actual translations.

---

## v1.6.34 — 2026-05-19

Operators can now turn the free tier on or off from the admin panel. Until this release every new portal sign-up automatically got a free subscription with 1 device and 10 GB — fine as a try-before-you-buy default, but operators running a paid-only service had no way to opt out short of hand-editing the database.

### Added

- **Settings → Free tier** in the admin panel. Single switch: "Offer free tier to new customers". Defaults to **on** so existing installs behave exactly as before. Flip it off and every new sign-up arrives with no subscription at all; the client portal Dashboard then shows a **Choose a plan** call-to-action instead of the usual stat cards, and the device-create endpoint refuses to issue a peer until the customer has purchased a plan.
- **`GET / POST /system/subscription-settings`** admin API for the toggle. Backed by `system_config.enable_free_tier` so the value survives restarts and propagates without an `.env` rewrite.
- **`needs_plan: true`** field on `GET /client-portal/subscription` when the toggle is off and the user has no subscription. The portal renders the no-plan state from this flag instead of treating the missing sub as an error.

### Behaviour

- `SubscriptionManager.ensure_subscription()` and `create_user()` both check the toggle before auto-creating a free row. The same gate covers the Telegram client-bot signup path.
- The portal `/plans` page no longer paints a "Current" badge on the Free tier when the user actually has no plan — previously it could mislead someone who'd just been told to pick something.
- `Plans` page selection / payment flow is unchanged; turning the toggle off only blocks the *auto-grant*, not paid upgrades or admin-issued subscriptions.

---

## v1.6.33 — 2026-05-19

PayPal, NowPayments and CryptoPay webhooks now actually reach their handlers. Until this release every webhook delivery for those three providers returned `404 Not Found` and the matching customer payment never auto-completed.

### Fixed

- **`/webhooks/paypal`, `/webhooks/nowpayments`, `/webhooks/cryptopay` all 404'd** because the generic `@router.post("/webhooks/{provider_name}")` catch-all (which dispatches to plugin providers like Stripe / Mollie / Razorpay / Payme) was registered in source order *before* the three dedicated routes. FastAPI matches route templates in registration order, so a `POST /webhooks/paypal` hit the catch-all first; the catch-all explicitly raised `404` for `paypal / nowpayments / cryptopay` (since those need their own handler signatures), and the dedicated routes underneath were dead code. From the provider's seat: webhook delivery looked permanently broken — the provider kept retrying, gave up, and the customer's payment stayed `pending` until an admin manually approved it from the panel. Same class of bug as the Stripe webhook fix in v1.6.27 (`Event.get()` AttributeError) and the v1.6.28 ADMIN_API_URL drift: a routing layer silently dropped real customer events. The catch-all is now registered *after* the dedicated handlers so FastAPI picks the right one for each URL.

### Audit summary

While diagnosing this, ran a full audit of every payment provider against every class of bug we fixed for Stripe between v1.6.20–v1.6.32. Other providers are clean:

- Plugin loader (v1.6.22): all four plugins (Stripe / Mollie / Razorpay / Payme) load via the same fixed loader path on both admin and portal processes.
- `PaymentMethod` ENUM (v1.6.25): all six provider names (`STRIPE`, `MOLLIE`, `RAZORPAY`, `PAYME`, `CRYPTOPAY`, `NOWPAYMENTS`) added in the right (uppercase) form for SQLAlchemy's enum serialization.
- Webhook payload parsing (v1.6.27, Stripe `Event.get()`): Mollie / Razorpay / Payme parse `json.loads(body)` directly on the raw bytes, so they never hit the SDK-object-stripped-of-`.get()` shape that broke Stripe. PayPal / NOWPayments / CryptoPay do the same in their dedicated route handlers.

End-to-end verified on a live install: forged-signature webhooks now reach `paypal_webhook` (returns `400 Invalid webhook signature`), `nowpayments_webhook` and `cryptopay_webhook` (return `503 not configured` when keys aren't set) instead of all three returning `404`.

---

## v1.6.32 — 2026-05-18

Stripe Checkout can now offer Alipay, WeChat Pay, SEPA Debit and any other payment method the operator has enabled in their Stripe Dashboard. Defaults to cards only so nothing changes on installs that haven't opted in.

### Added

- **`STRIPE_PAYMENT_METHODS` env var** (`stripe_provider.py`). Comma-separated list of Stripe `payment_method_types` to enable on every Checkout Session — e.g. `card,alipay,wechat_pay,sepa_debit`. Defaults to `card` so existing installs keep their current behaviour. WeChat Pay needs `payment_method_options.wechat_pay.client="web"` for Checkout to work; the provider adds that automatically when `wechat_pay` is in the list, so operators don't have to know about the API quirk.
- **Help block in admin Settings → Payment → Stripe** explaining the new env var. A standard tooltip question mark expands to the full setup steps: (1) enable the method in Stripe Dashboard → Settings → Payment methods, (2) add it to `STRIPE_PAYMENT_METHODS` in `/opt/vpnmanager/.env`, click Save & Connect. The portal service restart that already happens on Save picks up the new env. Each value listed must already be enabled on the operator's Stripe account, otherwise Stripe rejects Checkout Session creation with a 400.

---

## v1.6.30 — 2026-05-18

Follow-up to v1.6.29: the "Hide from customer portal" toggle in the admin UI now actually toggles. The hide direction worked already; unhide silently re-sent `customer_visible=false` on every click.

### Fixed

- **`Hide → Show` direction of the customer-visibility menu item never flipped the server back.** `ServerResponse.from_server()` is an explicit field-by-field constructor (not `from_attributes` / `from_orm`), so any new column on the `Server` model has to be added to its body to flow into the API response. v1.6.29 added `customer_visible` to the Pydantic schema and to the SQLAlchemy model, but the line `customer_visible=getattr(server, 'customer_visible', True)` was missing from `from_server`. `GET /api/v1/servers` therefore always returned `customer_visible=True` for every row, regardless of what the database stored. The Vue toggle button's label and the `next = !(server.customer_visible !== false)` calculation both read that field, so the admin's local view of the server stayed `visible=true` even after a successful hide PUT, and the next click computed `next = false` and re-sent `customer_visible=false`. From the admin's seat: "I clicked hide, the button still says Hide, every click does nothing". Adding the missing constructor line in `from_server` makes the response carry the real column value and the toggle starts behaving the way it always read in the template.

---

## v1.6.29 — 2026-05-18

Admin can now hide test / staging servers from the customer portal's location picker without deleting them.

### Added

- **`servers.customer_visible` toggle.** New `BOOLEAN NOT NULL DEFAULT true` column on the `servers` table (alembic migration `036_srv_visible`). Defaults to `True` for every existing row so no behaviour change on upgrade — admin can flip a server `False` from the Servers card menu when they want it kept around for internal testing but not offered to subscribers.
- **`GET /client-portal/servers`** now filters by `customer_visible = True`. The admin-side `GET /api/v1/servers` still returns every row (admin sees test boxes), only the customer-facing list narrows.
- **`POST /client-portal/wireguard/create`** rejects with 404 if the customer tries to create a device on a hidden server — defence in depth in case a stale frontend or a forged request slips through the picker filter.
- **Admin UI**: new menu item on each server card ("Hide from customer portal" / "Show in customer portal") that toggles `customer_visible` and a `Hidden` badge on the card so the admin sees at a glance which servers are gated. EN/RU/DE/ES/FR strings included.

---

## v1.6.28 — 2026-05-18

Client portal shows the customer's devices again on installs that ran `configure-web-access.sh` to put SSL on the admin panel — the script bumped the admin API to a new internal port but didn't propagate the new URL to the portal process, so the portal's "list my devices" call was hitting nginx HTTPS with plain HTTP and silently returning zero results.

### Fixed

- **Portal dashboard shows zero devices while the subscription card says "1/1 used".** Reported as "devices became invisible after migrating a server", but the migration was a red herring — the bug applied to any install where `configure-web-access.sh` had been run in `portal_admin_domain` or `portal_admin_ip` mode. That script puts nginx with a Let's Encrypt cert on the admin panel's public port (10086 by default) and moves the python admin process to `API_PORT=10087` so they don't conflict. `ADMIN_API_URL` in `.env` (used by the portal process to call the admin process's internal endpoints) is left at the legacy default `http://localhost:10086` — pointed at the HTTPS-only nginx port. Every `GET /api/v1/internal/clients/by-ids` from the portal then gets `400 The plain HTTP request was sent to HTTPS port` back from nginx, the `AdminAPIClient.get_clients_by_ids` catch-all logs the error and returns `[]`, and the dashboard renders zero devices even though the database row + WG peer are both fine. The limit check (`POST /wireguard/clients`) reads device count straight from the DB and didn't see the disconnect, so it kept rejecting `Add Device` with `device_limit_reached` — the operator saw a "0/1, can't add, can't delete" device list that still worked over VPN.

### Changed

- **`client_portal_main.py`** now derives the default `ADMIN_API_URL` from `API_PORT` (`http://localhost:${API_PORT}`) instead of hardcoding `:10086`. Bumping `API_PORT` alone is now enough to keep the portal pointed at the right place — no separate `ADMIN_API_URL` knob needed for the common case.
- **`scripts/configure-web-access.sh`** writes `ADMIN_API_URL=http://localhost:${API_PORT}` to `.env` in both `apply_mode_none` and `apply_domain_mode` paths, so the variable can't drift away from the API port the script just set. Defensive — covers the case where an operator's `.env` was populated under a different version of the script.

---

## v1.6.27 — 2026-05-18

Stripe webhooks now actually mark the payment as paid on their own — operators previously had to approve every successful card payment by hand from the admin panel.

### Fixed

- **Real Stripe webhook deliveries 400'd while the diagnostic page reported them as fine.** `stripe.Event` (what `Webhook.construct_event` returns once a signature passes) is a `StripeObject` in stripe-python 7+, not a `dict` subclass — `.get()` was dropped from the public surface even though `[…]` subscripting and attribute access still work. Our `process_webhook` did `event.get("type", "")` immediately after verification, which raised `AttributeError: get` on every real delivery; the wrapping route caught it as `Exception` and returned 400 to Stripe, so Stripe retried a few times and then gave up. Customers paid successfully on Stripe Checkout, but the panel's payment row stayed `pending` and the subscription never activated until an admin manually clicked "Approve" in the admin payments view. The diagnostic page in Settings → Payment → Test happened to work because it builds its own JSON-dict event and never goes through `construct_event`, masking the bug. The handler now normalizes the Event to a real `dict` via `event.to_dict_recursive()` (with a `dict(event)` fallback) right after signature verification, so all the downstream parsing is impervious to whichever Stripe SDK version is installed. Verified end-to-end: signed `checkout.session.completed` POST → 200, payment row flips to `completed`, subscription transitions to `ACTIVE` with the correct `expiry_date`.

---

## v1.6.26 — 2026-05-18

Granting or renewing a subscription that was previously cancelled or expired now starts the new period fresh instead of stacking on top of leftover days from the cancelled cycle.

### Fixed

- **`cancel → admin grants 1 month` resurrected the cancelled subscription with the leftover days added on top of the new month.** `SubscriptionManager.upgrade_subscription` / `renew_subscription` set `expiry_date = max(old_expiry, now) + timedelta(days=duration)` for any subscription with a future `expiry_date`. That makes sense for an active subscription being extended mid-cycle (the customer keeps the days they already paid for), but it's wrong for a cancellation — the customer's cancel was meant to end the period, and `manager.cancel_subscription` keeps `expiry_date` intact only because the original design lets the user enjoy the rest of the paid period before the downgrade. So an admin grant after cancel walked back the cancellation: status flipped to ACTIVE, and the leftover days from the cancelled cycle stacked under the new period (cancel with 15 days remaining + grant 30 days → 45 active days instead of 30). Both methods now snapshot `was_terminated = status in (CANCELLED, EXPIRED)` before flipping to ACTIVE and use that flag to decide whether to stack: active → stack as before, cancelled / expired → start counting from now. Active-subscription extension (the original use case) is unchanged.

---

## v1.6.25 — 2026-05-18

Stripe (and Mollie/Razorpay/Payme/CryptoPay/NOWPayments) checkout now actually completes the invoice write — the third part of the bug that v1.6.22 → v1.6.23 → v1.6.24 chipped away at.

### Fixed

- **Card-provider invoice creation still 500'd in v1.6.24** with `invalid input value for enum paymentmethod: "STRIPE"` (note the casing) even though v1.6.23 added `'stripe'` to the Postgres ENUM. Root cause: SQLAlchemy's `Enum(PaymentMethod)` column writes the enum MEMBER NAME, not its value. `PaymentMethod.STRIPE` (with `value="stripe"`) serializes to `'STRIPE'` in SQL. The DB ENUM had `'stripe'` (lowercase) but the INSERT was sending `'STRIPE'` (uppercase), so Postgres rejected it. Two fixes shipped together:
  1. Migration `035_pm_upper` adds the UPPERCASE values (`'STRIPE'`, `'MOLLIE'`, `'RAZORPAY'`, `'PAYME'`, `'CRYPTOPAY'`, `'NOWPAYMENTS'`) that SQLAlchemy actually emits, matching the existing uppercase scheme (`'BTC'`, `'USDT_TRC20'`, `'PAYPAL'`, etc.). The lowercase v1.6.23/v1.6.24 values stay (Postgres has no `DROP VALUE`) but are harmless dead weight — no code path writes them.
  2. `client_portal.create_invoice` now wraps the provider string in `PaymentMethod(data.provider)` before handing it to `SubscriptionManager.create_payment`. Previously a raw string `'stripe'` flowed through, which then crashed on `f".. via {payment_method.value}"` in the subscription-manager logging call right after the INSERT — even when the ENUM finally accepted the row, the next line raised `AttributeError: 'str' object has no attribute 'value'` and the response was still 500.

### Why this took three releases

The v1.6.23 migration attempted to side-step a mistakenly-assumed Postgres "ALTER TYPE in transaction" restriction by setting `isolation_level="AUTOCOMMIT"` on the bind. That returned a new SQLAlchemy Connection wrapper without actually escaping alembic's outer transaction, so the migration left `alembic_version` un-bumped, health-check noticed `current != head`, and auto-rollback restored the previous release. v1.6.24 dropped the AUTOCOMMIT hack — at which point the lowercase ENUM values went in cleanly, exposing the second bug (SQLAlchemy writes member name, not value), which v1.6.25 fixes by adding the correct UPPERCASE values plus the string-to-enum conversion at the write site. End-to-end verified by creating a real Stripe Checkout session against the customer-facing portal API and confirming the `cs_live_…` URL came back with the invoice row committed.

---

## v1.6.24 — 2026-05-18

Re-ship of v1.6.23's `paymentmethod` ENUM migration without the broken AUTOCOMMIT trickery that made it look like it ran while leaving `alembic_version` un-bumped — auto-update rolled the whole release back when the health check noticed.

### Fixed

- **v1.6.23 auto-update failed with `Alembic revision mismatch: current=033 head=034`.** Migration `034_pm_card` wrapped its `ALTER TYPE ... ADD VALUE` statements in `bind.execution_options(isolation_level="AUTOCOMMIT")` to side-step Postgres's old "cannot run inside a transaction" restriction. That call returns a new SQLAlchemy `Connection` wrapper but does NOT commit or close alembic's outer transaction — the underlying DBAPI connection is still inside the transaction alembic opened to bump `alembic_version`. The result on packaged installs: the ALTER TYPE statements either ran on a state that got rolled back, OR raised silently, leaving alembic in a half-applied state where the ENUM migration looked complete but `alembic_version` still read `033`. update_apply.sh's post-update health check (`alembic current` vs `alembic heads`) caught the mismatch, exited with code 1, and auto-rollback restored the previous release + PostgreSQL dump. So nobody actually got the new ENUM values, every Stripe checkout still 500'd, and the panel kept showing "Update failed: update_apply.sh exited with code 1".
- Migration now just calls `op.execute("ALTER TYPE paymentmethod ADD VALUE IF NOT EXISTS '<v>'")` directly. Postgres 12+ allows this inside a transaction provided the new value isn't read in the same transaction, which is the case here — we only add values, no INSERT references them in `upgrade()`. `IF NOT EXISTS` keeps the migration idempotent across re-runs (relevant when an admin has already added values manually as a workaround).

---

## v1.6.23 — 2026-05-18

Follow-up to v1.6.22: card-provider invoices stop 500-ing at the database write. The Postgres ENUM that backs `client_portal_payments.payment_method` was missing the values the code already writes.

### Fixed

- **Stripe (and Mollie/Razorpay/Payme) invoice creation 500s with `invalid input value for enum paymentmethod`.** The portal's `POST /client-portal/payments/create-invoice` handler writes the provider id verbatim into `client_portal_payments.payment_method` for hosted-checkout providers — `'stripe'`, `'mollie'`, etc. That column is a Postgres ENUM type called `paymentmethod`, created originally with only crypto + paypal/usd/eur values; the type itself rejects any string it doesn't recognize, so the INSERT fails at commit time with `psycopg2.errors.InvalidTextRepresentation: invalid input value for enum paymentmethod: "stripe"`. From the customer's seat the Stripe Checkout session created successfully (`cs_live_…` URL was already minted by Stripe's API), but the portal returned 500 and they saw "Failed to create invoice" without ever being redirected to checkout — and the orphaned Stripe session was never recorded locally. Added the missing values (`stripe`, `mollie`, `razorpay`, `payme`, `cryptopay`, `nowpayments`) to the `PaymentMethod` Python enum and shipped Alembic migration `034_pm_card` that does `ALTER TYPE paymentmethod ADD VALUE IF NOT EXISTS '<value>'` for each, with `IF NOT EXISTS` for re-run safety. The migration runs at AUTOCOMMIT isolation so it works on Postgres <12 where `ALTER TYPE` is non-transactional. Downgrade is a no-op — Postgres has no `DROP VALUE` and recreating the type would copy every row for a metadata-only change.

---

## v1.6.22 — 2026-05-18

Follow-up to v1.6.20/v1.6.21: payment plugins (Stripe, Mollie, Payme, Razorpay) now register on the client-portal process too, not just the admin process. Saving payment settings in the admin auto-restarts the portal so it picks up the new keys.

### Fixed

- **Payment plugins missing from the customer-facing portal even after v1.6.21.** The admin process (`main.py api`) and the client-portal process (`client_portal_main.py`) run as separate systemd services with separate Python interpreters. v1.6.20 fixed the plugin loader in the admin process, and the admin's diagnostic + `/api/v1/system/payment-test/stripe` saw Stripe as Active — but the portal process has its own copy of the `client_portal` module and its own startup lifespan, which never imported the `plugins/payments/*` files at all. So `/client-portal/payments/providers` (served by the portal) returned `[{nowpayments, configured:false}]` while the admin's diagnostic returned the full provider list, and customers saw the empty-fallback crypto picker in the Payment Method modal. The portal's lifespan now runs the same `importlib.import_module("plugins.payments.<stem>")` loop the admin does (with the same pyarmor-safe import path), so Stripe / Mollie / Payme / Razorpay register on both processes from a single set of env vars.
- **Hot-reloading payment settings only updated the admin process.** `POST /api/v1/system/payment-settings` instantiates each provider and sets it on `client_portal.<provider>_provider` — but that mutation lands on the admin process's copy of the module, not the portal's. The portal kept serving stale (or absent) provider state until a manual restart. The save handler now best-effort `systemctl restart`s `vpnmanager-client-portal.service` after writing the env file, so the next customer request hits the portal with the fresh keys loaded. `check=False` + `timeout=10` so a missing systemctl (Docker, dev installs) doesn't 500 the settings save.

---

## v1.6.21 — 2026-05-18

Client portal: card payments (Stripe + similar gateways) now actually appear in the customer-facing payment picker, device counters stay consistent across display and limit-check, missing translations no longer leak as raw keys, and plan cards spell out what's in each tier in plain English.

### Fixed

- **Card payment providers were invisible in the Choose-Plan → Payment-Method flow.** The picker rendered a hardcoded crypto-currency grid (USDT/BTC/TON/…) for any provider other than `paypal`. So even when admin Settings showed Stripe as Active and `GET /client-portal/payments/providers` correctly returned `{id:"stripe", type:"plugin"}`, choosing Stripe in the picker still pushed the user into a "select your crypto" screen — Stripe Checkout never opened. The modal now classifies each provider as `card | paypal | crypto`, and `card` providers (Stripe, Mollie, Razorpay, Payme) skip the currency picker entirely and go straight to the gateway's hosted checkout URL. The `selectedCurrency` watcher resets the currency when the operator flips between provider types, so the next `POST /client-portal/payments/invoice` call doesn't 422 with "currency not supported by stripe". Card-style providers get a `💳` icon next to the existing `💎` / `🔗` / `🅿️`.

- **Device counter inconsistency: dashboard shows `0/1` but Add Device returns `409 device_limit_reached`.** The display path (`GET /client-portal/wireguard/clients`) fetched the linked client IDs from `ClientUserClients` and then asked the Admin API for the actual `Client` rows — orphan links (rows pointing at a `Client.id` that's been deleted from the admin side, for any reason: manual cleanup, migration, schema reset) silently dropped out, so the dashboard rendered as if those devices didn't exist. The limit check on `POST /client-portal/wireguard/clients`, however, used the raw `ClientUserClients` count via `_get_user_client_ids`, which still saw the orphan rows and refused to add a new device. From the subscriber's seat the dashboard says "you have 0 devices, max 1" while every Add Device click fails with "limit reached". `_get_user_client_ids` now `JOIN`s against `Client` so orphan rows are filtered out at the source, making both paths agree. `GET /client-portal/subscription` and the traffic-aggregation query were switched to the same helper so the dashboard, the limit check, and the over-limit banner all read the same number.

- **i18n keys leaking to the UI as raw text.** Four keys (`dash.deviceLimitReached`, `dash.openUpgrade`, `pay.promoPlaceholder`, `pay.applyPromo`) existed in the Vue code but not in any locale file. `vue-i18n` falls back to returning the key itself as a truthy string when a translation is missing, which defeats the `t(key) || 'English fallback'` defensive pattern in the codebase — the truthy key wins and customers see literal `dash.deviceLimitReached` in their device-limit confirm dialog and `pay.promoPlaceholder` in their promo-code input. All four added to en/ru/de/es/fr with real translations.

### Changed

- **Plan-card description on the Choose Plan step** went from the cryptic `1 dev · Unlim · Max` to plain English: `Up to 1 devices · Unlimited data · Max bandwidth` (and equivalent phrasings on ru/de/es/fr). New keys `pay.maxDevices`, `pay.unlimitedData`, `pay.trafficGb`, `pay.maxBandwidth` added to all five locales.

---

## v1.6.20 — 2026-05-17

Hotfix: payment plugins (Stripe, Mollie, Payme, Razorpay) now register correctly at startup on production installs.

### Fixed

- **Payment plugins silently fail to register on package-built installs.** The startup loader in `src/api/main.py` was using `importlib.util.spec_from_file_location` to import each plugin from `plugins/payments/*.py`. That helper bypasses Python's package import hooks, so for any plugin that ships as part of a packaged install (where the `plugins/payments/` directory is treated as a package with an active import-time runtime in the package `__init__`), the module body executed in a degraded context and `PROVIDER_CLASS = …` at the bottom of each plugin file never bound. The loader then saw `PROVIDER_CLASS = None`, logged nothing, and moved on — leaving `client_portal.stripe_provider` (and friends) as `None` even though the admin had saved valid keys and `test_connection()` was passing against Stripe's API. Symptom in the wild: admin Settings → Payment shows "Stripe Active", but the client portal's `/payments/providers` endpoint returns only NowPayments (or the empty-state fallback), so customers never see a card-payment option. The startup loader now uses `importlib.import_module("plugins.payments.<stem>")`, which goes through the normal package import path and lets every plugin register properly. Dev/source-checkout installs were unaffected — the bug only surfaced on packaged customer deployments, which is why it shipped undetected. Affects all four card/crypto plugins (Stripe, Mollie, Payme, Razorpay) equally.

### Workaround for existing installs (pre-1.6.20)

If you're on an older build and Stripe isn't showing up in the client portal even though admin Settings says "Active": open admin Settings → Payment → Stripe and click Save & Connect once more. The hot-reload path on save (in `POST /system/payment-settings`) uses normal `from plugins.payments.stripe_provider import StripeProvider` and registers the provider in the running process correctly. The new build makes this stick across restarts; until you upgrade, every service restart will need a fresh Save click.

---

---

## v1.6.19 — 2026-05-17

AmneziaWG obfuscation parameters (Jc/Jmin/Jmax/S1/S2/H1-H4) are now editable from the panel after server creation, with three smart-fill paths so an operator migrating to a new AWG box can preserve existing client configs without re-issuing anything.

### Background

AmneziaWG packets carry per-server-unique header magic (`H1`-`H4`) plus shared junk parameters (`Jc/Jmin/Jmax/S1/S2`). Every client config bakes these values into its `[Interface]` section; the kernel module on the server side must match exactly or the handshake fails. Until now the panel generated these randomly on first server creation and offered no way to change them afterwards — fine for greenfield installs, painful for migrations: spin up a replacement AWG box with the same private key and the new auto-generated H1-H4 silently break every previously-issued client config. Operators had to either reissue all configs (annoying at scale) or `psql` the panel's DB directly (annoying and risky).

### Added

- **"Edit obfuscation params" menu item on AmneziaWG server cards.** Opens a focused modal with all 9 values, validation, and an atomic save flow: DB update → `awg.conf` rewrite on disk (local or via agent/SSH for remote boxes) → `awg-quick down/up` to make the kernel module pick up the new headers. Operators get one consistent "save & restart" UX whether their AWG server is local, behind SSH, or behind the HTTP agent.
- **"Copy from another AWG server" dropdown.** When the panel has more than one AWG server (typical migration: old box + new box both still registered), pick the source server from a dropdown and click Copy — all 9 values inherit in one click. Same-keypair candidates are listed first and tagged "same keypair" since they're the obvious-right-answer for migrations.
- **"Auto-fill from a working client config" paste box.** Fallback for when the old server entry is already gone from the panel. Paste any `.conf` that still handshakes against the old box (operator typically has one on their own device), the parser extracts `Jc/Jmin/Jmax/S1/S2/H1-H4` from the `[Interface]` section, and the 9 form fields fill instantly. Robust regex handles CRLF, tabs, mixed case, and the `H10`/`H11` false-positive trap. Plain WireGuard configs (no AWG fields) are rejected with a clear error.
- **Same smart-fill UX in the Add Server form's "Reuse obfuscation params" advanced section** — proactive migrators can pre-set params at creation time instead of editing afterwards.
- **`awg_jc/jmin/jmax/s1/s2/h1/h2/h3/h4/mtu` in `ServerUpdate` API schema** with `ge=1` validation on H1-H4 (zero is invalid for AWG kernel module). For non-AWG servers the route layer silently strips these fields rather than 422-ing.
- **Full RU/DE/FR/ES translations** for all 22 new strings in the modal.

### Changed

- **`ServerManager.update_server` `allowed_fields` whitelist** extended to include `awg_jc/jmin/jmax/s1/s2/h1/h2/h3/h4/mtu`. Pre-existing field-level gating still applies (unknown keys are silently dropped).
- **`PUT /servers/{id}` handler** detects whether any AWG obfuscation field is in the update payload and, if so, runs `save_server_config` + `restart_server` via `asyncio.to_thread` after the DB commit. Non-AWG updates (rename, endpoint, etc.) still skip the interface bounce. If the config push fails after the DB write succeeds, the API returns 500 with an actionable message pointing at the manual Apply Config + Restart fallback — operator can retry without losing the saved values.

---

## v1.6.15 — 2026-05-16

Dashboard "Traffic used" card now matches the "Traffic over time" chart.

### Fixed

- **Client portal dashboard: "Traffic used" stat card stuck at 0.00.** The card was pulling `Subscription.traffic_used_total_gb`, which sums two columns (`traffic_used_rx`, `traffic_used_tx`) that no code path actually writes to — every traffic-counter update across the codebase targets `Client.traffic_used_rx/tx` on the per-device row, not the subscription summary. So the card always read back the SQLAlchemy default of 0, no matter how many gigabytes flowed through the peer underneath. The "Traffic over time" chart sitting right below it was already aggregating `TrafficDaily` rows correctly, which is why operators saw two contradicting numbers (e.g. card "0.00 GB", chart "52 MB"). The /dashboard/subscription endpoint now sums `Client.traffic_used_rx + traffic_used_tx` across the portal user's linked devices, so the card matches the chart and the derived `traffic_remaining_gb` / `traffic_percentage` come out right.

---

## v1.6.14 — 2026-05-16

SSL setup in Settings → Web Access got a thorough hardening pass: HTTP/2, HSTS, modern TLS, DNS pre-check before requesting a cert, and several fixes to long-standing rough edges.

### Added

- **DNS pre-check before requesting a cert.** The setup script now resolves your portal/admin domain and compares against the server's public IP before calling Let's Encrypt. If the A record points somewhere else (or hasn't propagated yet), you get a one-line error pointing at the actual issue instead of a 30-second `certbot` timeout with a wall of authorisation-failure text.
- **Port 80/443 conflict pre-check.** If anything other than nginx is already listening on port 80 or 443 (Caddy, a stray docker container, anything), the script aborts cleanly with the offending listener identified, instead of letting nginx start-fail mid-setup.
- **HTTP/2 + HSTS by default.** New nginx vhosts listen on `443 ssl http2` and send `Strict-Transport-Security: max-age=31536000; includeSubDomains` in HTTPS responses. Faster page loads, no accidental HTTP downgrade after the first visit.
- **TLS 1.2/1.3 with Mozilla-Intermediate cipher list and OCSP stapling.** Legacy TLS 1.0/1.1 paths are gone, session tickets are off (per Mozilla's forward-secrecy guidance), OCSP stapling resolves via Cloudflare/Google with a 5s timeout, and a 2048-bit DH group is generated once and reused on subsequent runs.
- **Hardening security headers** in HTTPS server blocks: `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy` denying geolocation/microphone/camera by default.
- **`--staging` flag** on `scripts/configure-web-access.sh`. Test the SSL pipeline against Let's Encrypt's staging endpoint without burning your real-cert rate limit. Useful when iterating on DNS or before opening rate-limited domains.

### Changed

- **`proxy_read_timeout` raised 60s → 300s.** Long admin operations (full backups, bulk imports) no longer 504 partway through.
- **WebSocket-ready proxy headers** in every HTTPS server block (`Upgrade`, `Connection: upgrade`, `proxy_http_version 1.1`).
- **Per-vhost access and error logs** under `/var/log/nginx/portal-*.log` and `/admin-*.log` — easier triage when something goes wrong on one of two domains.
- **`update_env_file` now takes an exclusive `flock`** on `.env.lock`, matching the Python panel's lock path. Concurrent shell + panel writers no longer corrupt `.env`.

### Fixed

- **CLI arguments silently overridden by `.env` during Web Access setup.** Submitting the Settings → Web Access form would fail with `Invalid email:` even though the email field was filled, because the script's `set -a; . .env` step immediately wiped the form-supplied values with the empty `.env` defaults the panel writes during install. CLI values are now captured before sourcing and restored after.
- **Duplicate `ssl_protocols` / `gzip` directive at http scope.** Ubuntu 24.04's stock `/etc/nginx/nginx.conf` already declares these at the `http {}` level. The previous script's params file re-declared them, breaking `nginx -t`. They now live inside each `server { }` block, where per-block scope is allowed regardless of distro defaults.
- **`certbot.timer` left masked.** If the timer had been disabled or masked for any reason, it stayed that way even after a fresh SSL setup, silently breaking auto-renew 90 days later. Now: explicit `systemctl unmask + enable --now certbot.timer` after issuance.

---

## v1.6.13 — 2026-05-13

Mikrotik auto-disable now actually removes the peer from the router, and the Online Users page gains a per-server filter.

### Fixed

- **Mikrotik clients stayed connected after their expiry timer fired.** `timer_manager._get_wg` was missing the `agent_mode == 'mikrotik'` dispatch branch. For a Mikrotik server (which has no `ssh_host`) the helper fell into the local-server path, ran `wg show <iface>` on the panel host where that interface doesn't exist, returned silently, and the DB flipped to `enabled=False` while the peer kept running on the operator's router. This was the fifth call site of the same dispatch pattern that 1.6.10 and 1.6.11 already covered in four other files — a missed file, not a new bug class. Manually-triggered Disable was never affected (it goes through `client_manager._get_wg`, which already had the branch).

### Added

- **Clickable server filter on the Online Users page.** The per-server pills above the table are now buttons. Click one to filter the list to that server; click the active pill or the new "All" pill to clear. The top counter and the by-server breakdown always reflect overall state, so the filter only narrows the table — it never hides connections from the totals. `serverFilter` is in-memory only, fresh page visits start unfiltered.

---

## v1.6.12 — 2026-05-12

Mikrotik adapter survives routers without the IPv6 package.

### Fixed

- **`get_interface_addresses` aborted entirely on routers without the IPv6 package.** RouterOS installs without `/system/package` "ipv6" return HTTP 404 on `/rest/ipv6/address`. The unconditional fetch raised through, poisoning the already-fetched IPv4 result. Visible effect: at "Add Server" time, the panel could not inherit the router's real WireGuard pool and silently fell back to the schema default (`10.66.66.0/24`) — leading to a pool/router mismatch the operator wouldn't notice until clients couldn't reach the new range. Now wrapped in try/except so IPv4 inherit completes and `ipv6` is left `None` on routers without v6 support.

### Verification

Adapter behaviour is now covered by an end-to-end test suite against a mock RouterOS REST server: 53 checks across interface discovery, peer CRUD, bandwidth queues (`/queue/simple`), handshake parsing, transfer counters, address-pool inheritance with link-local filter, IPv6-package-missing fallback, auth-failure surface, multi-peer delete-server cleanup, and `RemoteServerAdapter` routing. Previous mikrotik releases (1.6.0 – 1.6.11) shipped without this; tests are now part of the development workflow.

---

## v1.6.11 — 2026-05-12

Polish pass for Mikrotik servers — Health page, server menu, and error messages now treat RouterOS-managed servers correctly.

### Fixed

- **Health page reported Mikrotik servers as offline.** The health checker (`server_checker.py`) had no Mikrotik branch and fell back to `_check_local`, which runs `wg show <iface>` against the panel host — where that interface doesn't exist. It came up "down" every tick. The Servers tab kept showing the server ONLINE because state reconciler writes `server.status` from its own (already Mikrotik-aware) path; the two views disagreed. A new `_check_mikrotik` reuses the RouterOS adapter to probe interface state and peer counts, producing a real WireGuard health record with handshake-recency-based "active peers" instead of nothing.
- **Server-row menu offered actions that don't apply to Mikrotik.** "Install Agent", "Install Proxy", "Install AmneziaWG", "Expand address pool", and "Migrate clients" were visible for Mikrotik servers. Install actions hit SSH/agent code paths and bounced with a generic error. Expand pool would update the DB but never reach the router. Migrate clients had no destination-write path for Mikrotik. All five are now hidden via `agent_mode === 'mikrotik'` checks. Rename, Export keypair, and Set Default remain available.
- **`/agent/install` returned a misleading error.** Mikrotik servers got "Cannot install agent on local server" — the wrong reason. Now the endpoint refuses with "Mikrotik routers are managed via the RouterOS REST API — no agent installation is needed."
- **`/servers/{id}/expand-pool` silently no-op'd on Mikrotik.** The endpoint would update the DB but never push regenerated config to the router. Now returns a 400 explaining that the address pool is configured in RouterOS itself (`/interface/wireguard`, `/ip address`) and inherited by the panel at adoption.

### Behaviour notes

- The Mikrotik adapter's `_check_mikrotik` does not collect system metrics — RouterOS exposes CPU/memory/disk via different APIs, and panel monitoring of the operator's box is out of scope. Health rows for Mikrotik servers show only interface and peer state.
- Auto-recovery (`state_reconciler._try_recover_interface`) already short-circuits for Mikrotik (added in 1.6.10) — the panel never auto-enables a wg interface the operator disabled on the router.

---

## v1.6.10 — 2026-05-12

Mikrotik servers now show live stats and online users.

### Fixed

- **Mikrotik servers stayed empty on the Clients tab and Online Users tab** even though the server itself reported ONLINE. Three handshake/state code paths still dispatched on `ssh_host` alone, so a server with `agent_mode='mikrotik'` (which has no `ssh_host` — it has `mikrotik_url` instead) silently fell into the local-WireGuardManager branch and tried to run `wg show` for an interface that doesn't exist on the panel host. Result: empty peer list → `last_handshake` never refreshed in the DB → both online lists stayed blank.
  - `state_reconciler._wg_manager` now routes mikrotik through `RemoteServerAdapter`.
  - `clients._enrich_handshakes` and the map-data endpoint now route mikrotik through `RemoteServerAdapter`.
  - `ManagementCore.get_client_full_info` (used by Client Portal and "client details" pages) routes the per-client handshake fetch through the adapter for mikrotik servers.
- **Auto-recovery no longer touches a mikrotik interface.** `state_reconciler._try_recover_interface` previously short-circuited only for SSH-agent servers; mikrotik servers slipped through and could be auto-enabled if the operator had disabled the router's wg interface on purpose. Now mikrotik mode is treated the same as the SSH-agent / agent-URL guard.

---

## v1.6.9 — 2026-05-12

Combined release: tier-definition cleanup, payment ladder split, and a broader feature-alias map that re-entitles legacy Pro / Business / Enterprise keys to features that have been added or renamed since the keys were originally issued.

### Changed

- **Tier definitions cleaned.** Removed flags that no code actually checks: `basic_management`, `wireguard_only`, `priority_support`, `bandwidth_limits`, `traffic_limits`, `expiry_timers`. They don't gate anything in the panel, and their presence in tier defs only confused the licence inspector. Existing signed keys still carry these flags harmlessly; nothing breaks.
- **Telegram bot flags collapsed into one canonical `telegram_bots`** present on every tier (FREE through Enterprise). Bot functionality depends on the operator supplying a token in `.env`, not on the licence. Legacy keys with `telegram_admin_bot`, `telegram_client_bot`, or `client_tg_bot` still satisfy `has_feature("telegram_bots")` via the alias map.
- **Payment ladder split into `nowpayments` (FREE+) and `payments` (Pro+).** `nowpayments` covers NOWPayments crypto on every tier. `payments` is required for card-processor providers (Stripe, Mollie, PayMe, Razorpay, PayPal, CryptoPay) and is Pro+ only. The `/api/v1/payments` prefix gates on `nowpayments` so the basic payment surface works on FREE; per-provider gating inside the router blocks card processors for non-Pro licences. The previous accidental `payments ← nowpayments` alias is removed.
- **`android_app` added to the Business tier.** Pro and Enterprise had it but Business didn't — a step missing from the ladder.

### Added

- **Broader legacy-compat alias map.** Newer canonical flags now resolve from the legacy tier marker that proves entitlement. `multi_server` (Pro+ marker) satisfies `mikrotik_adapter`, `payments`, `auto_backup`, `white_label_basic`, `traffic_rules`, `android_app`, `auto_renewal`, `promo_codes`. `proxy_protocols` (Standard+ marker) additionally satisfies `auto_renewal`, `promo_codes`, `nowpayments`. `white_label` (Enterprise marker) satisfies `corporate_vpn`, `manager_rbac`. FREE customers carry none of these markers, so the additions cannot accidentally entitle FREE installs.
- **Effective features in `/api/v1/system/license`.** The endpoint now returns the alias-expanded feature set so the frontend's gating matches the backend's `has_feature(...)`. UI feature-gated controls (the Mikrotik connection mode option being the most visible) no longer hide for licences that satisfy the feature via aliasing.
- **Sidebar tier badges** next to paid menu items (Backup, Traffic Rules, Promo Codes, Applications/RBAC). Surfaces the required tier (Starter / Pro / Business / Enterprise) when the active licence lacks the feature; items aren't hidden, which turns "stuff I can't use" into a soft-conversion prompt.

### Behaviour notes

- Existing customers on Pro, Business, or Enterprise see every entitlement they paid for, without re-activating. Run "Check for updates" in the panel, apply, reopen the page — feature surface repopulates from the alias-expanded `/system/license` response.
- FREE customers are unchanged: they retain `nowpayments`, `wireguard`, `amneziawg`, `client_portal`, and `telegram_bots`.
- Newly-issued activation codes carry the full feature set directly rather than relying on aliases.

---

## v1.6.7 — 2026-05-12

Fixes a UI startup gap where the licence feature list wasn't being fetched until a `FeatureGuard`-wrapped view was visited. Views that depend on `licenseStore.has(...)` directly — the most visible being Add Server's Mikrotik connection-mode option — would render with the default empty feature list and hide their gated UI even on licences that legitimately had the feature. The licence store now loads at app startup, and reloads automatically after login.

---

## v1.6.6 — 2026-05-12

Fixes a UI gating regression where licence-feature buttons (most visibly the Mikrotik connection-mode option in Add Server) stayed hidden for operators whose licence carries a legacy feature flag that the backend honours through aliasing but the frontend couldn't see. `/api/v1/system/license` now returns the **effective** feature set — raw features plus any canonical flag whose alias is satisfied — so frontend checks like `license.has('mikrotik_adapter')` resolve the same way the backend's `has_feature()` does. Operators with existing Pro / Business / Enterprise lifetime keys (which carry `multi_server` but not `mikrotik_adapter` explicitly) now see the Mikrotik option in the form without re-issuing their licence.

---

## v1.6.5 — 2026-05-12

**Per-peer bandwidth caps now work on RouterOS-managed servers**, closing the last functional parity gap between Linux-managed and Mikrotik-managed Pro-tier servers. Setting a Speed limit on a client backed by a Mikrotik server now provisions a `/queue/simple` entry on the router targeting that peer's IP. Linux servers continue to use `tc/htb` as before; only the dispatch and the RouterOS path are new.

### Added

- **`MikrotikWireGuardManager.set_bandwidth_limit(ip, mbps)` / `remove_bandwidth_limit(ip)`** mapping panel bandwidth operations to RouterOS `/queue/simple`. Each managed queue is named `flirexa-peer-<ip>` and carries a `managed by flirexa — do not edit` comment so it's easy to identify alongside the operator's own queues. Symmetric upload + download (same `max-limit` for both directions).
- **`get_bandwidth_limits()`** for inspecting / reconciling the live cap state on the router from panel-side code (returns `{ip: mbps}` for every panel-managed queue).
- **`RemoteServerAdapter` routes the existing `set_bandwidth_limit` / `remove_bandwidth_limit` calls** to the Mikrotik backend when `agent_mode == 'mikrotik'`. `TrafficManager.set_bandwidth_limit` no longer falls through to local `tc` for remote-managed servers; it delegates to the adapter unconditionally.

### Behavior notes

- A limit of `0` Mbps removes the queue entirely (`tc` and `queue/simple` both treat this as "no cap").
- Updating an existing cap rewrites the queue's `max-limit` in place — same name, same target, no flap of the existing traffic.
- Queues named `flirexa-peer-*` are the only ones the panel touches. Other queues you've configured on the router via WebFig, Winbox, or any tooling stay untouched.

---

## v1.6.4 — 2026-05-12

Three follow-ups to the RouterOS integration that ship in 1.6.2: the panel now picks up the router's existing address pool automatically, avoids handing out IPs already claimed by manually-added router peers, and surfaces aggregated peer transfer in server stats. Together these reduce the "fill in the same `/20` you already configured on the router" friction and prevent panel-allocated clients from colliding with peers added directly via WebFig or Winbox.

### Added

- **Address pool auto-inherits from the router** at server-create time for Mikrotik mode. The probe step now reads the WireGuard interface's IPv4 address from `/ip/address` and stores the matching `/N` network on the server row, so the operator doesn't have to retype it. If the operator passes an explicit non-default pool in the request, that value still wins (no surprise overwrite). IPv6 link-local (`fe80::/10`) is filtered out since it's not a usable client pool.
- **IP-allocation collision check against the live router** for Mikrotik servers. Before assigning a new client an IP from the pool, the allocator now queries the router's peer list and treats any peer's `allowed-address` as occupied alongside the panel's own DB records. Manually-added router peers (configs the operator set up before adopting the panel, or peers from other tooling on the same interface) are skipped instead of clashed with. Soft-fails to the DB-only view if the router doesn't respond, so client create doesn't break on transient connectivity blips.
- **Server stats include Mikrotik peer traffic.** `get_server_stats` and the bandwidth/traffic managers now route Mikrotik servers through the adapter (previously they fell through to a local `wg` command which doesn't apply). Aggregated `total_rx` / `total_tx` and per-peer last-handshake / transfer counters now come from the router's `/interface/wireguard/peers` over REST.

### Fixed

- **Subnet auto-shift no longer clobbers the router's pool.** The "interface already in use" / "subnet overlaps another local server" auto-shift block was running for Mikrotik servers too — they have no `ssh_host` and looked local. Adding a router as the third or fourth server would silently rewrite the just-probed pool with a bumped local default. Skipped for remote-managed modes, which include Mikrotik.
- **Listen-port auto-shift also skipped for remote-managed modes** for the same reason — port belongs to the router, not the panel host.

---

## v1.6.3 — 2026-05-11

**RouterOS / Mikrotik adapter is now a Pro-tier feature.** When this shipped in 1.6.2 it was unconditionally available on every install, including FREE. That was an oversight — managing a Mikrotik-hosted WireGuard server is a paid capability alongside multi-server orchestration and proxy protocols, and 1.6.3 gates it accordingly.

### Changed

- **`mikrotik_adapter` feature flag** added to the Pro / Business / Enterprise tier definitions. Selecting Mikrotik connection mode and submitting now requires the license to carry this flag; the API returns `403` with `license_feature_required: mikrotik_adapter` for licenses that don't.
- **The Mikrotik option in the Add Server form is hidden** when the active license lacks the feature — FREE and Starter operators no longer see it as an available choice.
- **Backwards-compatibility for already-issued Pro+ keys.** The feature alias table maps `mikrotik_adapter` ← `multi_server`, so existing lifetime Pro / Business / Enterprise keys (which carry `multi_server` but not the new flag) keep working as expected. No re-issue needed.

---

## v1.6.2 — 2026-05-11

**RouterOS support — manage WireGuard servers running on Mikrotik routers directly from the panel.**

A new "Connection" mode in the New Server form, alongside SSH: pick Mikrotik (RouterOS API), paste the router URL plus an API username and password, and the panel takes over peer management on that device. The router's WireGuard interface and its keypair stay where the operator set them up — the panel just talks to the device's REST API (port 80 by default, 443 when SSL is enabled). All the usual client lifecycle works the same as for SSH-managed servers: add client, disable/enable, delete, all the way through to the generated `.conf` that clients download from the portal.

### Added

- **Mikrotik connection mode** with three new fields on Add Server (RouterOS URL, API username, API password). On submit, the panel probes the router over REST, pulls the WireGuard interface's public key and listen-port from the device, and stores them on the server row — no need to type the pubkey by hand.
- **Client lifecycle parity with SSH mode.** Adding a client creates a peer on the router; disabling a client removes the peer (preserving the client's IP and PSK so re-enabling restores it identically); deleting a client removes the peer for good. Generated client `.conf` contains the router's real public key, verified to handshake end-to-end.
- **Connection mode is hidden for incompatible protocols.** RouterOS cannot run AmneziaWG (Linux-kernel-specific) or Hysteria2/TUIC. Selecting either of those server types in the Add Server form hides the Mikrotik option so an unsupported combination cannot be picked.
- **Translations** for the new form labels and hint banner in English, Russian, German, French, and Spanish.

### Fixed

- **Startup failure when `address_pool_ipv6` was stored as a host address rather than the network address.** Some installs ended up with `fd42:42:42::1/64` (the host form) saved on the server row, which then expanded to the invalid `fd42:42:42::1::1/64` at `wg-quick up` time and the kernel refused to bring the interface up. The composer now normalizes either form before writing the Address line, and the install bootstrap stores the network form consistently going forward.
- **Deleting a Mikrotik-managed server no longer touches the router's own interface.** Earlier in development this code path was sending a `disabled=true` to the router's WireGuard interface on server delete — surprising for an operator whose interface predates the panel. Now the panel only cleans up the peers it added itself.
- **The "interface already in use" check no longer false-positives on remote-managed servers.** Adding a Mikrotik server with `wg0` would fail if the panel host also had a local `wg0`, even though the two interfaces live on entirely different machines. The check is now scoped to local-mode servers, where it actually matters.

### Limitations

- Per-peer traffic counters and latest-handshake from Mikrotik aren't pulled into the panel's stats dashboards yet. The data is exposed by RouterOS over REST and will be wired into the panel in a follow-up release.
- Bandwidth caps for Mikrotik peers (Linux servers already have them via tc/htb) require a different mechanism on RouterOS (queue tree) — also queued for a follow-up.

---

## v1.5.100 — 2026-05-11

Translates the Let's Encrypt requirements banner on the proxy server create form. The three-line banner that appears when TLS mode is set to ACME was previously hardcoded in Russian and stayed Russian regardless of the selected UI language. All four strings (banner title plus three requirement bullets) now go through `vue-i18n`, with full translations in English, Russian, German, French, and Spanish. The lookups are wrapped in computed properties with try/catch and a literal English fallback, matching the defensive pattern adopted in 1.5.96 for the Clients form.

---

## v1.5.99 — 2026-05-11

Fixes a regression where Hysteria2 and TUIC installations were rejected with an upgrade prompt on installs running paid licences issued before some internal feature-flag names were normalized. `LicenseInfo.has_feature` now consults an alias table, so a renamed canonical flag still matches its legacy predecessor on existing signed keys. Customers don't need to re-issue or re-activate their licence.

---

## v1.5.98 — 2026-05-10

Internal release — no user-visible changes in the panel.

---

## v1.5.97 — 2026-05-10

Internal release — no user-visible changes in the panel.

---

## v1.5.96 — 2026-05-10

The Customer field is back in the New Client form. The 1.5.94 attempt rendered the Clients page blank for some users when the inline `$t()` calls in the template hit a transient i18n state during initial mount. This release moves the lookups into computed properties wrapped in try/catch, so a missing key or an i18n hiccup returns a hard-coded English fallback instead of taking the parent component down with it. Translations also got a quick simplification — removed the apostrophe-via-concatenation in the Russian string and replaced em-dashes with plain ASCII so the bundle has no edge-case characters that could confuse a minifier.

---

## v1.5.95 — 2026-05-10

Hotfix for the Clients page going blank after 1.5.94. The new Customer field in the New Client form was triggering a render error in the deployed bundle on some installs, leaving the entire Clients view as a white screen. Reverted that input from the form. The backend `customer_email` column and the Settings → Device limits panel are kept — the cap still works for any peer tagged via the API directly. The form input will return in a follow-up release after the rendering path is fixed properly.

---

## v1.5.94 — 2026-05-10

Translations for the `Customer` field on the New Client form. The 1.5.93 build referenced i18n keys that didn't exist yet, so non-English locales fell through to a hardcoded English fallback. Added `clients.customerEmail`, `customerEmailHint`, and `customerEmailPlaceholder` for English, Russian, German, French, and Spanish.

---

## v1.5.93 — 2026-05-10

Per-customer device cap that works when the operator manages peers entirely from the admin panel. The portal-side `max_devices` from 1.5.91 only enforced when subscribers self-served through the client portal — operators who add every peer manually weren't covered. This release adds an admin-side path.

### Added

- **`Customer` field on the New Client form.** Free-text identifier (typically email or username) the operator types when creating a peer. Peers with the same value are treated as belonging to the same real-world customer.
- **Settings → Device limits → Max devices per customer.** Single global cap. When an operator tries to create a (N+1)th peer with a `customer_email` that already has N active peers, the create returns `409 Conflict` with a structured payload, and the New Client modal shows an inline message instead of a JSON blob. `0` disables enforcement.

### Removed

- **Endpoint-flap key-sharing detector** introduced in 1.5.92. The "count distinct source IPs in last 24h" signal was unreliable in practice — a single mobile client jumping between cell towers tripped it constantly while two devices behind one home NAT remained invisible. The `peer_endpoint_log` table is left in place (it stops growing because nothing writes to it) but the `endpoint_distinct_24h` field is dropped from the admin client response.

---

## v1.5.92 — 2026-05-10

Advisory monitoring for possible key-sharing. The `max_devices` cap from 1.5.91 stops a subscriber from creating more peers than their plan permits, but it doesn't catch the case where they copy one config to multiple devices and use it from different networks. This release surfaces a soft signal so operators can investigate.

### Added

- **`peer_endpoint_log` table** records the source IP each peer is observed handshaking from. Written by the state reconciler on every tick (no extra polls), only when the IP differs from the last observation for the same peer — keeps the table small. Works on both agent and SSH-mode servers.
- **`endpoint_distinct_24h` field on the admin client detail response.** Counts the number of distinct source IPs seen for a peer over the last 24 hours. Anything ≥ 2 is a soft warning that the same WireGuard config may be in use on multiple devices on different networks. False positives are common (mobile clients flapping between WiFi and LTE, NAT'd corporate networks), so the operator sees the count and decides what to do. No automatic action is taken.

---

## v1.5.91 — 2026-05-10

Per-subscriber device limit polish. The `max_devices` cap on tariffs already worked, but the user-facing experience around it was thin: the rejection error was a bare string, downgrades silently let users sit over-limit forever, and there was no audit trail for operators trying to see how often subscribers hit the ceiling.

### Added

- **Soft-downgrade banner in client portal.** When a subscriber switches to a smaller plan mid-cycle and ends up with more devices than the new plan allows, all existing devices keep working until renewal. The dashboard now shows an inline warning telling the user how many to remove and that the oldest will be pruned automatically at the next billing date if they don't pick.
- **Auto-prune at renewal.** When the subscription renews for a new period, any excess devices over `subscription.max_devices` are soft-disabled (oldest first) so the next cycle starts within the plan limit. Prune is idempotent and falls back gracefully if individual disables fail.
- **`device_limit_events` audit log.** New table records every block ("user tried to add device 4 of 3") and every auto-prune decision so operators can review activity from the admin panel and decide whether to raise plan caps.

### Changed

- **Device-limit rejection now returns a structured `409 Conflict`** with `code`, `max_devices`, `used_devices`, and `current_tier`. The portal renders an inline "Upgrade plan?" prompt instead of a bare error toast.

---

---

## v1.5.90 — 2026-05-10

Resilience pass for the agent connection. Brief upstream blips (NAT shuffles, ISP route changes, port-forward hiccups) were flipping servers to "unreachable" several times an hour even though they were only out for a few seconds. The panel reported what it saw, but the UI shouldn't alarm operators over 5–30s drops.

### Changed

- **Brief connectivity blips no longer flip a server to "offline".** Agent `/health` and `/stats` requests now retry once (health) or twice (stats) with a short backoff before declaring the agent unreachable. The first try still succeeds on a healthy network, so the latency budget is unchanged for normal operation.
- **Last-known agent state is cached for 30 minutes.** When the agent does fail every retry, the dashboard returns the previous successful poll tagged `is_stale=true` with an age in seconds, and the server status reads `degraded` ("showing data from 45s ago") instead of `offline`. Peer counts no longer collapse to zero during a transient drop.

The fix is panel-side only — agents do not need to be reinstalled, and the SSH/local code paths are untouched.

---

## v1.5.89 — 2026-05-09

Critical fix for license enforcement. On a FREE-tier install with multiple servers (where some are remote and share an `interface` name like `wg0` with the panel host's local interface), the suspension sweep was running `wg-quick down` locally for every "excess" server. If a remote wireguard server's interface field collided with the local one, this tore down the panel's own tunnel and dropped every connected client.

### Fixed

- **License enforcement now respects local-vs-remote dispatch.** `_stop_server_runtime` routes through `ServerManager.stop_server`, which uses `RemoteServerAdapter` for remote hosts. Stopping a remote server can no longer touch the local interface.
- **State reconciler auto-recovers downed local interfaces.** When the periodic reconciler detects a local interface is down on a server expected to be ONLINE (and not deliberately stopped, suspended, or remote), it attempts `wg-quick up`. Rate-limited to one try every 5 minutes per server. Operators no longer have to SSH in to bring an interface back after an unexpected drop.

---

## v1.5.88 — 2026-05-08

Favicon now matches the brand logo. Both admin and client portal ship with `flirexa-logo.png` as the favicon, so the browser tab icon and the in-app logo are visually identical.

### Changed

- **Favicon = brand logo.** Replaces the previous SVG mark in both `admin` and `client portal` with the same PNG used for the in-app logo. If you set a custom favicon via Settings → Branding, that override still wins.

---

## v1.5.87 — 2026-05-08

Reverts the favicon change from 1.5.86. Operators who had their own branding configured did not appreciate the default favicon being swapped on them.

### Changed

- **Favicon reverted to the previous mark.** `icon-192.svg` and `icon-512.svg` in both admin and client portal now match the pre-1.5.86 design. If you had a custom favicon configured via Settings → Branding, it continues to work as before.

---

## v1.5.86 — 2026-05-08

Brand cleanup. The panel and client portal now ship with Flirexa branding by default — title, manifest, favicon, and OpenAPI doc title all read "Flirexa". The shared favicon is the bird-in-flight mark from flirexa.biz on a purple gradient, identical between admin and portal.

### Changed

- **Default app name is now "Flirexa"** across both frontends, the manifest.json files (PWA install name), the apple-mobile-web-app-title, and the OpenAPI `title`. The Settings → Branding override still works, so any operator who has set a custom app name will keep it.
- **Default favicon is the Flirexa bird mark** (white silhouette in flight on purple-gradient ground). Admin panel and client portal serve the same SVG so the look is consistent across the two surfaces. The previous generic "S" placeholder is gone.

---

## v1.5.85 — 2026-05-08

End-to-end fixes for the backup restore path. Restore from a panel backup now works without manual intervention — earlier you had to stop services by hand or the restore would silently hang on database locks. Verified on a fresh stand: full create → mutate → restore → verify cycle, byte-for-byte recovery in three seconds.

### Fixed

- **`/backup/restore/database` no longer hangs on its own database connections.** Two interacting bugs caused `pg_restore --clean` to deadlock against the running panel: BackupManager held a stale read-transaction from `_get_storage_config` (because SQLAlchemy keeps a snapshot open with `autocommit=False`), and the panel's worker pool had additional connections still holding table locks. Now `_get_storage_config` rolls back its read immediately, and `_restore_database_from_file` terminates competing connections to the target database via `pg_terminate_backend` as a belt-and-braces step before invoking pg_restore.
- **`restore_database` now stops services automatically.** It always needed to (without a stop, pg_restore deadlocks on table locks held by the API), but earlier versions left this to the operator. New default `stop_services=True` mirrors what `restore_full_system` already does. Pass `stop_services=False` only from a CLI context where the API is already not running. The full sequence is: stop api+worker+client-portal → run pg_restore → restart all three. Total downtime under 2 seconds in our stand test.

### Why this matters

Before this release, clicking Restore in the panel would hang or fail — and the failure mode was opaque (just a 500 error after a long timeout). The restore code was correct in isolation, but never tested end-to-end against a live panel. This is now verified on a real stand with the same database schema and SystemConfig population a customer would have.

---

## v1.5.84 — 2026-05-08

Path mismatch fix that was producing two backup directories on a single host depending on which code path created the archive.

### Fixed

- **Manual backups now land in the same directory as scheduled backups.** `BackupManager._get_storage_config` was using a default of `<file>/../backups` (two `.parent` climbs), while the scheduler at `src/api/scheduler.py` was using `<file>/../../backups` (three `.parent` climbs). On an installed host, this meant manual API-triggered backups went to `<install>/src/backups/` while the nightly auto-backups went to `<install>/backups/`. Both defaults now resolve to `<install>/backups/`. `SystemConfig.backup_path` overrides this when set, so installs that explicitly configured a backup directory are unaffected.

---

## v1.5.83 — 2026-05-08

Backup section consolidated into one place. Settings, schedule, storage, and the backup history list used to be split across two views (Settings and the standalone Backup page) with two different APIs and at least one broken button on the Settings copy. Now everything lives on the Backup page, with one API surface, fewer footguns, and a couple of real bugs fixed along the way.

### Changed

- **Single backup page.** The Backup view now contains the status overview (schedule status, storage type and free space, total backups, latest backup), the backups list with verify/restore/delete actions, the schedule form (frequency, time, retention, autocleanup), and the storage form (local path or network mount with credentials, mount, unmount, test write). The Settings page no longer has a duplicate copy — it just links across.
- **Single backup API surface.** All backup endpoints now live under `/api/v1/backup/*` (settings + storage + operations). The previous `/api/v1/system/backup-*` endpoints were removed; the frontend's API client points everything to the new paths.

### Fixed

- **Network storage password no longer appears in `ps aux` or journalctl.** Mount commands previously passed the SMB password via `-o password=X`, which means anyone with read access to the process list or system journal could see it. Now we write a 0600 credentials file to a temp location, pass it as `-o credentials=/tmp/...`, and remove it after the kernel has read it.
- **Backups silently landing on local disk when the network mount was down.** Previous behavior: if the mount point existed as a directory but was not actually mounted, `os.makedirs` and the tar write would succeed against the underlying local filesystem — a "successful backup" that you could not restore from on the network share. Now `BackupManager.create_full_backup` calls `ensure_storage_ready()` first, which verifies the mount via `mountpoint -q` and attempts one auto-mount with stored credentials before allowing the backup. A truly unmounted-but-existing-as-dir target now fails the backup outright with a clear error.
- **Backup delete in the Settings duplicate UI was calling a method that did not exist.** The old code used `backupApi.deleteBackup`, but only `backupApi.delete` was exported. Clicks landed in a try/catch and silently produced an alert message — the backup itself stayed on disk. The Settings duplicate is removed; the working delete on the Backup page is the single path now.

### Added

- **Storage status endpoint with disk-usage information.** `GET /api/v1/backup/storage/status` returns the resolved target path, mount status (for network), used/free/total bytes, percent-used. Drives the new "free / total" badge on the Backup page so the operator sees the truth about disk pressure rather than guessing.

---

## v1.5.82 — 2026-05-08

The async-to-thread-pool migration that started in 1.5.81 (hot paths) extended to the rest of the API. Combined with a larger database connection pool and a fix for an N+1 query in the server list, the panel now stays fast even when many tabs are open and many users are working in parallel.

### Changed

- **129 API endpoints converted from `async def` to `def`.** This is the same fix as 1.5.81 but applied across the entire API surface (admin auth, app accounts, bots, client portal, clients, corporate, internal, payments, portal users, promo codes, servers, share, system, tariffs, traffic rules, updates). Anything that does synchronous SQLAlchemy or SSH/agent I/O without an `await` now runs in FastAPI's thread pool. The single event loop is no longer the bottleneck for any common request, so a slow query on one route does not stall every other route.
- **Database connection pool grown.** Was 5 base + 10 overflow (max 15 connections). Now 20 base + 30 overflow (max 50). When most routes were on the event loop, 15 connections was plenty because only a few threads ever touched the DB at the same time. With the thread pool serving up to 40 concurrent requests, 15 became a hard ceiling that backed up under load. 50 keeps headroom under Postgres's default `max_connections=100` while removing the bottleneck.
- **Connection pool now uses `pool_pre_ping=True`.** After a Postgres restart or network blip, the next handful of requests previously returned 500 because pooled connections were dead but unused. Pre-ping costs one round-trip per checkout in exchange for no first-request errors after recovery.
- **Single grouped query for client counts on the server list.** `/api/v1/servers` was doing one extra `SELECT COUNT(*)` per server in the response, on top of the list itself. With 6 servers that meant 7 sequential DB queries for one request. Replaced with a single `GROUP BY` query, so it is now exactly 2 queries regardless of fleet size.

### Added

- **`scripts/audit_async_routes.py`.** Walks every route handler in `src/api/routes/` and fails if any is declared `async def` but has no `await` and uses sync I/O (SQLAlchemy, requests, subprocess). Run it from the repo root before committing or in CI to prevent the same class of slowness from creeping back in. Whitelists legitimate async patterns (websockets, file uploads, async-with).

### Why this matters

If you run more than two or three servers, or have more than one operator working in the panel at the same time, this is the release that makes things feel instant. The 1.5.81 fix unblocked the live-poll path on the Servers and Clients pages. 1.5.82 unblocks the rest: payments, support tickets, traffic rules, portal users, dashboards, settings. Combined with the larger DB pool, the panel now scales smoothly past the point where 1.5.80 visibly stuttered.

---

## v1.5.81 — 2026-05-08

Panel responsiveness fix for operators with multiple servers. The Servers and Clients pages would noticeably lag (2-3 seconds per request) on installs with 5+ servers because the hot-path API endpoints serialized on a single event loop. They now run in a thread pool, so concurrent fan-outs progress in parallel.

### Fixed

- **`/api/v1/servers`, `/api/v1/clients`, and `/api/v1/servers/{id}/bandwidth` no longer block the event loop.** These endpoints had been declared `async def` but used synchronous database and SSH/agent calls inside, which meant every request held the loop until done. With 6 servers, the live-poll fan-out (one /servers call + one /bandwidth per server) queued behind itself and the last request waited 2+ seconds. Now declared as `def` so FastAPI runs them in its thread pool — unrelated requests no longer wait on each other.

### Why this matters

If you have only one or two servers you may not have noticed; the queue depth was small enough to absorb. With 5+ servers the live-poll cycle alone was enough to keep the loop saturated, producing the "Request timed out" toasts you may have seen even on a perfectly healthy panel. After this update, the bandwidth fetches all start at the same instant and finish in parallel, and the badges/values populate in roughly the time of the slowest individual server rather than the sum of all of them.

---

## v1.5.80 — 2026-05-08

Make a broken agent obvious instead of silent. When an agent stops responding, the panel now surfaces the problem with a one-click recovery path.

### Added

- **Top-bar warning indicator.** Red pill with a count of unreachable agents, visible from every page. Clicking jumps straight to the Servers page where the full banner lives. Refreshes on route change, on tab focus, and every 30 s in the background — so you'll spot a dead agent even if you're sitting on Dashboard.
- **Unreachable-agent banner on the Servers page.** Lists every server whose agent circuit-breaker is open, how long it's been unreachable, and offers two buttons per row: **Switch to SSH mode** and **Retry now**. The text spells out *why* the panel feels slow ("requests to X time out") so the cause-and-effect is no longer guesswork.
- **Red pulsing badge on affected server tiles.** The agent badge in the server card flips from blue to red and pulses when its breaker is open, making the bad server impossible to miss when scanning the grid.
- **Backend: `agent_breaker` field on `GET /servers`.** Each server in agent mode now reports `{open, fails, opened_seconds_ago, reopens_in_seconds}`. Lets dashboards and integrations show breaker state without hitting a separate health endpoint.
- **Backend: `POST /servers/{id}/agent/breaker/reset`.** Force-clears the in-memory breaker so the next request probes immediately. Backs the "Retry now" button — useful right after fixing a firewall rule or restarting the agent service.

### Why this matters

The 1.5.79 circuit breaker stopped a dead agent from dragging the whole panel down, but the user-facing symptom — "panel feels slow, occasional 'Request timed out' toasts, no clear cause" — was still there. Operators had to know to dig into Manage Agent menus to find the recovery options. With the banner and the top-bar pill, the diagnosis and the fix are surfaced together, in plain English: *which* server is unreachable, *for how long*, and a one-click switch to SSH mode that clears the lag instantly.

---

## v1.5.79 — 2026-05-08

Circuit-breaker hardening so a single permanently-dead agent in the operator's server list doesn't keep dragging the whole panel down with periodic re-probe attempts.

### Changed

- **Exponential backoff on the agent circuit breaker.** First trip stays at 60 s as before, but sustained failure (6+ in a row) extends the open-window to 5 minutes, then 30 minutes (9+), then 1 hour (15+). A successful call resets the counter and the agent is treated as healthy immediately. Surfaced when an operator left a decommissioned server in the panel — every 60 s the breaker re-opened, one stats fetch tried to connect to the dead agent, hit a connect-timeout, and the whole fan-out (Clients page, Online Users page, Dashboard) paused for that 5 s window. With backoff, a long-dead agent gets retried at most once per 30–60 minutes after the first 5 minutes, making its presence in the panel essentially free.
- **Split connect/read timeouts on the agent client.** Connect is now a fixed 5 s (TCP handshake plus DNS — sub-second on healthy networks, 5 s catches reasonable WAN latency). Read stays at 30 s. Earlier the same value was used for both, so a connect-timeout to a dead agent could take up to the full 30 s, blocking a request worker for that long.

### Why this matters

Operators with multiple servers were seeing intermittent "Request timed out — check your connection" toasts and a generally laggy panel whenever one of the servers was unreachable. The fan-out path (handshake enrichment, bandwidth aggregation) had to talk to every server, and one slow agent meant the slowest determined the response time. With per-agent breaker state and shorter connect timeouts, the slowest healthy agent now sets the floor — dead ones contribute essentially zero overhead.

### Logging

Breaker state changes log only on threshold crossings (fails=3, 6, 9, 15) instead of every poll cycle. Quieter journal, easier to spot when an agent is genuinely degrading vs. routine flaps.

---

## v1.5.78 — 2026-05-08

Expand-pool validation relaxed: pool overlap is now only blocked between servers on the **same physical machine** (same `ssh_host` value, or both panel-local). Two WireGuard servers on different boxes don't share a kernel routing table, so their pools can overlap without breaking anything — each box NATs its own range to the internet independently.

The previous strict check was treating any two servers with overlapping pools as a conflict, even when the servers were on completely separate VPS instances. Surfaced when a real prod had three servers with identical /24 pools across three different machines, all of which the operator wanted to expand — validation refused all of them. With this relax, the check now only fires for true same-machine collisions where both interfaces would compete for the same kernel routes.

End-to-end re-tested on a production setup: a remote agent-mode server, /24 → /20, peers reconnected on the next handshake cycle, no client disconnects beyond the brief expected window.

---

## v1.5.77 — 2026-05-07

A bundle of operator-facing additions and a stack of bug fixes shaken out of a real prod incident on the new Expand Address Pool feature.

### Added — Servers

- **Expand address pool from the UI.** A new menu entry on each WireGuard / AmneziaWG server card opens a modal that grows the pool to a wider CIDR. Validates that the new range strictly contains the old one (no client gets orphaned), refuses overlap with another server's pool, regenerates the WG config and bounces the interface so the new mask is live in-kernel. Existing clients keep their IPs and reconnect within seconds.

### Added — Clients page

- **Time-limited share link** on every client row. Generates a `/share/<token>` URL valid for 10 minutes (configurable up to 1 hour) that the operator can hand to a customer in any chat — they download their `.conf` from the link without logging in. Tokens are stored in a dedicated audit table with first-use timestamp and IP.
- **Post-create modal.** Adding a client now pops a modal showing the new client's details, a freshly-issued share link with a live countdown, plus quick shortcuts to download the config or show a QR code.
- **Just-created highlight that pins to the top.** New rows glow green at row 0 of the list for ~60 s regardless of the active sort, then drop back into normal order. Single-slot — if you create a second client during the window, the highlight transfers to the latest.
- **Robust clipboard fallback.** The share modal's Copy button now uses `navigator.clipboard` first, then `document.execCommand` for HTTP-served panels, then selects the URL with a hint to press Ctrl+C / ⌘C as the last resort.

### Fixed — agent + panel bounce reliability

- **Address line on regenerated server configs no longer hardcodes /24.** The pre-1.5.77 generator emitted `Address = X.X.X.1/24` regardless of the actual pool prefix, which silently broke any non-/24 pool. Surfaced when Expand Pool tried /20 in production. Now uses the real prefix from the server's stored pool.
- **`AmneziaWGManager` start/stop now pass the explicit config_path to `awg-quick`.** On installs that put the AWG config at a non-default location, the bare-interface argument made `awg-quick` fail to find the config and return non-zero. Stop/Start buttons in the UI silently failed for AWG agents in this state. Fix is end-to-end: panel-side and agent-side variants both pass the path now.
- **`wg-quick` / `awg-quick` non-zero exit on PostDown is no longer fatal when the interface is actually down.** Bringing an interface down can leave the script with a non-zero exit code if a stale iptables rule or `ip route del` line trips on cleanup, even after the link itself is gone. The previous code reported "stop failed" and refused to bring the interface back up — leaving customers disconnected. Now we re-check the kernel: if the link is gone, the teardown achieved its goal.
- **`agent.py` `is_interface_up()` no longer raises HTTP 500 on a down interface.** It was using the strict `run_cmd` helper which raised on any non-zero exit, and `wg show` exits non-zero when the interface doesn't exist — so the very function whose job was to answer "is the interface up?" blew up the moment the answer was "no". Now returns False cleanly.
- **`agent.py` `/interface/up` and `/interface/down` are tolerant of wg-quick non-zero exit when the kernel state is already correct.** Same PostDown / PostUp cleanup story as the panel-side fix, applied to the agent's HTTP endpoints. The expand-pool agent-path bounce now succeeds reliably.

### Fixed — UI

- **"Request timed out — check your connection" toast no longer fires for every background poll cycle.** The global axios timeout was raised from 15 s to 30 s (covers fan-out latency to multiple agents), and `useLivePoll` now bracket every tick with a `silent` flag so request failures from background polls degrade quietly. User-driven request failures still surface as before.
- **`Update server connection timeout` no longer fires on healthy networks during transient DNS / TLS handshake spikes.** Connect timeout for the manifest fetch raised from 5 s → 10 s, read timeout 8 s → 15 s. Total still well under the panel's axios envelope.
- **Online Users dark theme now actually applies.** The `prefers-color-scheme: dark` block was dead code because the panel uses a manual `[data-theme="dark"]` attribute toggle. Same fix applied to the Live indicator pill, the share-link modal, the migration modal, and the just-created highlight.
- **Live indicator removed from the Dashboard.** Headline counters load once on mount and stay put — no flicker, no constant polling. The world map's location markers still refresh every 30 s as before. Live monitoring lives on the dedicated Online Users page now.

### Build tooling

- **`push_test.sh` auto-bumps the patch number** when the current `VERSION` is already on the test channel. Closes a footgun where a re-uploaded same-version tarball was a silent no-op for any panel that already pulled it. Use `--in-place` if you really want the legacy overwrite behaviour. Stable refusal now suggests the next-likely version in the error message.

### Tests

- 20 cases in `test_lifetime_protected.py` continue to pin the lifetime-protected license model behaviour.
- 3 cases in `test_bootstrap.py::TestUninstallPreservesDataPlane` continue to guard the agent-uninstall data-plane preservation contract.

---

## v1.5.70 — 2026-05-07

A bundle of operator-facing polish for the Clients page and Online Users page, plus a critical update-pipeline fix flushed out by a prod incident on 1.5.67.

### Added — Clients page

- **One-click 10-minute share link.** New action button (link icon, info-coloured) on every client row generates a public, time-limited URL the operator can paste into Telegram or any chat — the customer downloads their `.conf` from that URL with no panel login. Default lifetime 10 minutes (configurable 1 minute–1 hour via the API). Tokens are tracked in a dedicated audit table with first-use timestamp and IP.
- **Post-create modal.** Creating a new client now pops a modal showing the new client's name, server, IP, the freshly-issued share link with a live countdown, plus an Edit shortcut. No more searching the list.
- **Just-created highlight that pins to the top.** While a row is glowing (60 s after creation), it sits at position 0 of the list regardless of the active sort, and the table jumps to page 1 so the new row is actually on screen. After the highlight expires, sorting reverts to whatever the user picked. Single-slot — if you create a second client during the window, the highlight transfers to it; the previous one fades back to normal immediately.

### Fixed

- **Update pipeline no longer auto-rolls-back on idempotent failures.** Migrations now skip `CREATE TABLE` / `CREATE INDEX` operations when the target already exists, so a partially-applied previous attempt doesn't trap the next install in a permanent rollback loop. Surfaced by a real prod incident: a transient migration crash left an orphan table behind, every subsequent `apply` hit the same crash, the post-update health check saw the Alembic revision mismatch, and triggered a rollback that didn't fully clean up. The cycle stopped being self-healing.
- **Auto-update silent-failure fixed.** The auto-apply path in `auto_check.py` was importing a function from the wrong module (`is_newer` from `.manager` instead of `.checker`), which silently broke every auto-apply attempt for who-knows-how-long. Manual "Apply update" was unaffected, which is why nobody had noticed.
- **Alembic migration failures now log a full traceback at ERROR level** instead of a one-line WARNING that swallowed the root cause. The next failure will tell you exactly which migration choked and on which row.
- **Dark theme contrast pass** on the new Online Users page, the Live indicator pill + interval picker, and the share-link modal. The previous dark CSS was gated on `prefers-color-scheme`, but the panel uses a manual `[data-theme="dark"]` attribute toggle instead — the OS-dark gate never fired, so muted text was rendering at light-mode contrast on a dark background and ended up effectively invisible. All dark variants now ship via the actual selector the panel uses.

### Build tooling

- **`push_test.sh` auto-bumps the patch number** when the current `VERSION` is already on the test channel. Closes a footgun from earlier this week — re-uploading a tarball under the same version number is silently a no-op for any panel that already pulled it, so "I shipped a fix" felt like nothing changed. Use `--in-place` if you really want to overwrite the existing test build (rare). Refusal on stable now suggests the next-likely version in the error message.

---

## v1.5.66 — 2026-05-06

A dedicated **Online Users** page in the main navigation — a live, read-only monitor of who's currently connected to your VPN, with per-client real-time speeds. Shipped together with a calmer Dashboard.

### Added

- **Online Users page** in the Main section of the sidebar, between Dashboard and Clients. Read-only, no Create/Edit/Delete buttons — just a clean list of who's connected right now. Each row shows the client name (with a coloured initial avatar generated from the name so the same person always gets the same colour), the server they're on, their IPv4, when they last handshook, **their current download/upload speed**, and total session traffic. The page filters down to peers whose last handshake is within the past 3 minutes.
- **Live indicator with interval picker** dedicated to monitoring duty — defaults to 5 s cadence (vs. 15 s on the Clients page). The picker (Off / 5s / 15s / 30s / 1m / 5m) saves per page in localStorage, so each operator keeps their own rhythm.
- **Per-client live speed** — the table and mobile cards both show current download/upload rates in Mbps (or kbps under 1 Mbps). Numbers update every poll cycle. Background-keepalive traffic (under 5 kbps) is shown as `idle` in italics rather than as `0.00 Mbps`, so the screen reads cleanly when nobody's actively streaming.
- **Per-server breakdown chips** under the page header — small pill for each server with how many of the page's online peers it owns. Useful for spotting if all activity is on one node.
- **"X seconds ago" / "X minutes ago"** timestamps that tick every second locally, between network polls. The page feels alive even at 1 m polling cadence.

### Changed

- **Dashboard no longer auto-refreshes**, and the Live indicator is gone from there. The headline counters (Total/Active clients, Servers, etc.) load once on mount and stay put — no flicker, no constant polling. The world map's location markers still refresh every 30 s as before. If you want a live view, the Online Users page is the place for that now.

### Why this split

The Clients page is the one with the create/edit/delete machinery — full CRUD, filters, bulk actions. The Online Users page is purely *who's on the VPN right now*, with no controls to accidentally hit. Two different mental models, two separate pages.

### Mobile

- Native card layout on phones — avatar + name + server + IP stacked into a clean row, with download/upload speed and total traffic on subsequent dashed rows. No horizontal table scrolling, no truncated values.

---

## v1.5.64 — 2026-05-05

A new license model: lifetime-protected. Pay once, run forever, and migrate to a new server yourself without contacting us.

### Added

- **`lifetime_protected` license type.** Locally-validated signature like a regular lifetime license — the panel never depends on the license server to keep working — but a 24h telemetry heartbeat lets the vendor spot installations sharing the same key (clone detection). This is the new sweet spot between "online subscription that we can revoke" and "pure offline lifetime that we can't see at all".
- **Owner name and email in the signed payload.** Settings → License now shows who a key belongs to without a database round-trip. Useful when an operator hands the box off and the next person needs to see who originally bought it.
- **Self-service server transfer.** Lifetime-protected customers see a `Migrate to new server` button that generates a one-time code (`MIGRATE-…`). They install the panel on the new box, paste their license key, then paste the code into the `Have a transfer code?` field. The next heartbeat tells the license server about the legitimate fingerprint change — no clone alert. **The old server self-decommissions 3 days later** ("burning bridge"), so the customer is forced to actually move rather than running the same key on two boxes indefinitely.
- Three new endpoints: `POST /api/v1/system/license/transfer/{initiate,apply,cancel}`.

### Operator UI

- Owner card under the License panel — name + email in a soft-bordered block. Hidden when the field is missing (older keys keep working, just don't show owner info).
- Migration modal with an explicit warning step ("3-day countdown starts on Generate"), a copy-to-clipboard code field, and a step-by-step list of what to do on the new server.
- A live countdown badge on the License card while a migration is pending (`This server stops working in 2d 14h…`), with a Cancel button to abort if the move was a misclick.

### Tests

20 new pytest cases in `test_lifetime_protected.py` — payload generation, license-type detection from raw `LICENSE_KEY`, heartbeat interval selection per type, online-validator never-block guarantee for lifetime/lifetime_protected, migration code round-trip + tamper detection + refusal for wrong license type, decommission countdown including idempotency on repeated Generate clicks.

---

## v1.5.63 — 2026-05-05

Live auto-refresh on the panel — the Clients list and Dashboard counters now update on their own, no more F5 to see who's online.

### Added

- **Live indicator with interval picker** in the top-right of the Clients page and Dashboard. Click the badge to choose how often the panel re-fetches: Off / 5s / 15s / 30s / 1m / 5m. Choice is persisted per page in `localStorage`, so each operator keeps their own cadence across reloads.
- **Auto-pause when the tab is in the background** (Page Visibility API). A panel left open in another tab won't keep waking the agents up — polling resumes the moment the tab is brought back into focus.

### How it looks

The badge sits inline with the page title actions. Green pulsing dot = polling, grey = paused (tab hidden), pale grey = Off. The current interval is shown next to the label ("Live · 15s"). Reduced-motion users get a steady dot instead of the pulse, dark-mode contrast is handled.

### Under the hood

A small `useLivePoll` composable (Vue 3) wraps `setInterval` + visibility handling + cleanup on unmount, so adding live behaviour to other pages later is a one-liner. The backend already injects fresh `last_handshake` from each agent on every `GET /api/v1/clients`, so what feels like "live" is just the frontend asking for the snapshot it was already getting on demand.

---

## v1.5.62 — 2026-05-05

Two production-hardening fixes after a panel-saturation incident on a multi-server install.

### Fixed

- **One unreachable agent can no longer slow the whole panel.** A single agent whose management port had become unreachable from the panel host could pile up 30-second connect-timeouts in the FastAPI threadpool — every `/bandwidth` poll for that one server stacked another blocked worker, until the UI itself stopped responding. The agent client gains a host-keyed circuit breaker: after 3 consecutive connect failures the panel skips that host for 60 s, returns immediately, and unblocks the threadpool. After the cooldown expires, the next failure re-opens the breaker for another 60 s instead of letting timeouts leak through forever.
- **"Uninstall agent" no longer disconnects customers.** The panel's per-server agent uninstall flow used to bring down the WireGuard interface and remove its `.conf` file as part of cleanup — disconnecting every connected peer because the operator clicked an agent-management button. This was over-engineering: the install side already rewrites the config and bounces the interface on the next install, so the destructive teardown was unnecessary. `uninstall_agent` now defaults to control-plane-only (systemd unit, agent code dir, agent's own iptables rule). The `delete_server` flow that purges an entire server record still tears the data plane down, opted into via a new `purge_vpn_interface=True` flag.

### Tests

Three new regression tests pin the new uninstall behaviour: control-plane uninstall keeps `wg1` up and `/etc/wireguard/wg1.conf` intact (WG and AmneziaWG variants both covered); the explicit `purge_vpn_interface=True` flag still brings the interface down for the delete-server flow.

---

## v1.5.61 — 2026-05-05

Bundle of four fixes around the Migrate Clients flow, plus agent-mode interface control. All driven by operator-feedback.

### Fixed

- **Top Consumers / Bandwidth on the destination server** now resolves peer names across ALL servers, not just the current one. After a dual-active migrate, the destination's live WireGuard has the source's peers; their DB record stays on the source, so the panel previously fell back to public-key fragments. The new lookup finds the original client name and tags shadow peers with their source-server name.
- **Stop / Start now work in agent mode.** The agent (≥ 1.4.0) gains `/interface/up` and `/interface/down` endpoints calling `wg-quick`. The panel's Stop button no longer returns a misleading "Failed to stop server" error. Older agents that don't expose the endpoint surface a clearer message asking the operator to re-bootstrap.
- **Migrate Clients refuses keypair-mismatched targets.** When the source and destination have different WireGuard public keys, every client config (which pins the source's PublicKey) would fail to handshake on the destination — usually accidental selection. The API now returns HTTP 400 with `error: keypair_mismatch` and a helpful pointer to the "Reuse private key" Add Server toggle. Pass `force_different_keys=true` to override when you really do intend to re-issue every config afterwards.
- The Migrate Clients modal greys out destination servers with mismatched keypairs in the dropdown and shows a warning when no candidate matches the source's identity.

### Tests

Migration test suite extended from 4 to 6 cases — keypair-mismatch refusal and force-bypass paths are both under regression coverage.

### Note on agent re-bootstrap

The `/interface/up` and `/interface/down` endpoints are part of agent v1.4.0 (bundled in the v1.5.61 tarball). They take effect on a remote VPN node after the panel re-runs agent_bootstrap on it. Older agents keep working — they just continue to surface the friendlier "agent < 1.4.0" warning if you press Stop in the panel.

---

## v1.5.60 — 2026-05-05

UI polish on the dual-active migrate flow shipped in v1.5.59.

### Fixed

- The "Remove peers from old WG" checkbox in Migrate Clients now also unticks itself the moment "Keep clients on source server" is enabled. Previously it stayed visually ticked (just greyed out) even though the backend ignored it — the box and the actual outcome are now consistent.
- One-way only: turning "Keep on source" off again does not auto-re-tick "Remove from old", so the operator's last choice is preserved.

---

## v1.5.59 — 2026-05-05

Migrate Clients gains a dual-active "copy" mode for transitions where DNS hasn't fully propagated yet — clients keep working against both endpoints during the cutover window.

### Added

- **"Keep clients on source server (dual-active during DNS propagation)"** checkbox in the Migrate Clients modal. When ticked, the source server retains both its DB association AND its live WireGuard peers; the destination just gets the same peers added on top. While DNS is in flux, customer configs work against either endpoint depending on what their resolver returns.
- The new option automatically greys out the "Remove peers from old WG" toggle, since the two are conceptually mutually exclusive.

### Why

Previously the only ways to migrate were either a full move (clients leave the source for the destination) or a "kernel-only-keep" mode (peers stayed on source's WireGuard, but the DB still re-pointed and the source's panel showed it as empty). Neither preserved the dual-active state needed during a DNS transition. The new mode fills that gap: source stays visible and live, destination becomes additionally live, both honour the same client identities.

### How to complete the move later

When DNS has fully propagated, run Migrate again on the same selection without the new checkbox. That re-points the DB to the destination and removes the peers from the source's WireGuard, finishing the cutover.

### Tests

Four pytest cases cover the matrix (full move / kernel-only-keep / dual-active / dual-active+selective) and assert exactly which `add_peer` / `remove_peer` calls fire on each side. CI now has migration semantics under regression coverage.

---

## v1.5.58 — 2026-05-05

Internal release-pipeline hardening to prevent a v1.5.55-class regression from ever shipping again. Plus a small straggler from the v1.5.55→v1.5.57 cleanup.

### Fixed

- One leftover loguru-style `{}` placeholder in `src/modules/updates/manager.py` (a stdlib-logging file) — would have raised `TypeError` if the SUCCESS branch on update apply was reached. Reverted to `%-style`.

### Internal (dev-only)

- New static linter checks every `logger.X(...)` call against the file's actual logger source (loguru vs stdlib) and refuses any `{}`/`%`-style mismatch. Now wired into `push_test.sh` as a pre-flight gate, so a broken release can't reach the test channel — let alone production.

---

## v1.5.57 — 2026-05-05

Hotfix combining a v1.5.55 regression revert with the WG+AWG subnet-collision fix that was meant to ship as v1.5.56.

### Fixed

- **v1.5.55 regression: smoke-check fail on upgrade.** The mass `%s → {}` conversion in v1.5.55 also touched 6 modules that use stdlib `logging` (not loguru). Stdlib `logging` interprets `%s` but not `{}`, so on those calls the stdlib→loguru bridge raised `TypeError: not all arguments converted during string formatting` at startup. Smoke-check rolled the upgrade back. Reverted those 6 files to `%s` style — they were never loguru in the first place. Loguru-native files keep their `{}` style.
- **WireGuard + AmneziaWG subnet collision on the same host.** Adding a second VPN protocol on a host that already had one was using the same default client subnet (`10.0.1.0/24`), so the kernel routed that subnet through the last-up interface and the older interface's clients lost return traffic. Two-layer fix:
  - Add Server form now picks `10.0.1.0/24` for WireGuard and `10.66.66.0/24` for AmneziaWG by default. Switching the protocol updates the field unless the operator already typed a custom value.
  - Backend auto-shifts the third octet of the requested subnet when it overlaps an existing local server's pool, so direct-API callers (and the 2× WG / 2× AWG case) are also safe.

### Symptoms before the fix

- Created an AmneziaWG server alongside an existing WireGuard one (same host) → clients on the WireGuard server lost internet through the tunnel.
- Reverse case (WG added next to AWG) symmetric.
- Upgrading to v1.5.55 → smoke check failed, install rolled back automatically.

---

## v1.5.55 — 2026-05-05

Internal logging hygiene. No user-visible behaviour change, but logs in `journalctl -u vpnmanager-*` now render readably.

### Fixed

- **137 loguru calls** across 17 modules were using legacy `%s/%d/%f` placeholders, which loguru does not interpret — those messages were getting logged with literal `%s` markers visible (e.g. `[BV] FIN-2: client %d '%s' over traffic limit (%.0f/%.0f MB)`). Converted to loguru-native `{}` braces (with `{:.0f}` preserved where precision matters), so log output now shows the actual values.
- Touched modules include the business validator, payment recovery scheduler, plugin loader, license server-config, subscription manager, update manager, and the API/route layer.

---

## v1.5.54 — 2026-05-05

Internal build-tooling hardening. No user-facing changes — install / upgrade behaviour and product surface are identical to v1.5.53.

---

## v1.5.53 — 2026-05-05

The installer now tells you what it's actually doing and how long it should take.

### Added

- **Per-step progress bar** in `install.sh`: each of the 8 install steps prints its own ETA banner ("Installing system dependencies… (≈2m cold)") and a cumulative bar afterwards (`[████░░░░░░] 25% · 2/8 done · elapsed 2m 44s · ~3m 30s remaining`).
- **Total install estimate** printed during pre-flight, so you know up front whether the install is going to take 30 seconds (warm host) or 7 minutes (fresh Ubuntu / cold cache).
- The "AmneziaWG installing…" hang on fresh Ubuntu hosts (DKMS compile against current kernel headers — typically the slowest single step) is now visibly part of step 1/8, so it doesn't look stuck.

### Why

Previously the installer was silent for 60–180 seconds at a time during heavy steps (apt update with new PPAs, DKMS kernel-module build, pip install with C extensions). On a fresh VM this looked like a hang; "did it crash?" was a recurring support thread. The bar + ETA surfaces real progress without changing what the installer actually does.

---

## v1.5.52 — 2026-05-05

Fixes a real bug in the keypair-reuse flow shipped earlier: the toggle accepted the pasted private key but the server-creation path silently overwrote it with a freshly generated one, so the "replace a broken server" workflow produced a new identity instead of preserving the old one. Existing client configs (which pin the old PublicKey) couldn't handshake with the new box, and connecting through it gave no internet access.

### Fixed

- **Add Server with reused private key** now actually keeps the pasted key. The backend derives the matching public key from the supplied private key (`wg pubkey` / `awg pubkey`) instead of falling through to the discovery-or-regenerate fallback that overwrote both keys.
- New box created with the toggle now has the same identity as the old one, so existing `.conf` files keep working without re-issue.

### Symptoms before the fix

- After migrating clients to a new server created via "Reuse private key", clients couldn't reach the internet through the new box.
- Migrating back to the old box restored access (it still had the original keypair).
- Looking at WG configs on the new box revealed a different public key than the one pasted into the form.

---

## v1.5.51 — 2026-05-05

Starter tier capacity bump.

### Changed

- **Starter tier client limit raised from 300 to 500.** Existing Starter licences automatically pick up the new ceiling — no re-issue needed; the tier metadata is read live from the license manager. Gives solo operators meaningful headroom over the FREE tier (which stays at 80).

---

## v1.5.50 — 2026-05-05

UI follow-up to v1.5.48's Migrate Clients action: the modal now lets you pick which clients to move, instead of only doing bulk all-or-nothing.

### Added

- **Client picker** inside the Migrate Clients modal: scrollable list with checkboxes, all checked by default. Uncheck any to do a canary move (e.g. 5 clients to validate the new server, then come back and move the rest).
- **Filter box** (name / IPv4 / ID) for finding a specific client when the list is long.
- **All / None** quick toggles next to the selection count, e.g. `Clients to migrate (5 / 47)`.
- The Migrate button switches its label to **Migrate selected** when a subset is picked, and is disabled if zero clients are selected.

### Behaviour

- If every client stays checked, the API call is identical to the old bulk path — no regression for existing users.
- If a subset is picked, the request includes `client_ids` and the backend's existing pre-flight (already there since v1.5.48) refuses the move cleanly with a structured error if any of the chosen clients would collide on the target server.

### Translations

`migrateClientsToPick`, `migrateSelectAll`, `migrateSelectNone`, `migrateLoadingClients`, `migrateNoClients`, `migrateFilterPlaceholder`, `migrateFilterNoMatch`, `migrateSubsetHint`, `migrateSelected` — EN / RU / DE / FR / ES.

---

## v1.5.49 — 2026-05-04

UI follow-up to v1.5.48's keypair-reuse workflow: the "Server private key" field is now reachable from the **Add Server** form, not just from the API.

### Added

- **"Replacing a broken server? Reuse its private key" toggle** in the Add Server modal, directly under the SSH password input. Collapsed by default so the form stays simple for normal installs; clicking it expands a single 44-character WireGuard private-key field.
- The hint inside the toggle links back to v1.5.48's `Servers → ⋯ → Export keypair`, so the operator can paste the dead box's key straight in.
- Empty-input handling: if the field is left blank, the form drops it from the payload (the API requires exactly 44 chars when present, so an empty value would otherwise fail validation).

### Translations

`reuseKeyToggle`, `privateKeyLabel`, `privateKeyPlaceholder`, `privateKeyHint` localized in EN / RU / DE / FR / ES.

---

## v1.5.48 — 2026-05-04

Operations toolkit for server-replacement scenarios. When a WireGuard box dies or has to be rebuilt, you can now keep customers' configs working without re-issuing them.

### Added

- **Export keypair button** in the server menu (`Servers → ⋯ → Export keypair`). Reveals the server's private key + public key + listen port + endpoint + subnet (and AmneziaWG obfuscation parameters when applicable). Use the private key as the seed for a new server's `Private key` field — the new box accepts every existing client config without re-issuing.
- **Migrate clients** action in the server menu. Bulk-moves all clients (or a selected subset) from one server to another. Three operations in one transaction: re-points `server_id` in the database, removes peer entries from the old server's WireGuard, adds them to the new one. Idempotent and safe.
- **Selective migration** via the API: `POST /api/v1/servers/{id}/migrate-clients` accepts a `client_ids` list for canary moves before a full bulk migration.
- **Pre-flight IP conflict check** — if any moving client's IP is already taken on the target server, the API returns `HTTP 409` with a structured `conflicting_clients_on_target` payload, instead of crashing with `IntegrityError`. The replace-broken-box workflow (new server starts with 0 clients) is conflict-free by construction.
- Audit log lines for both operations: `[AUDIT] server.keypair.reveal actor=…` and `[AUDIT] server.clients.migrate actor=… from=…(…) to=…(…) moved=… failed=…`.

### Translations

All new admin strings (`exportKeypair`, `migrateClients`, `keypairWarning`, `revealKeys`, `keypairUseHint`, `migrateNow`, `migrateSyncRemote`, `migrateRemoveOld`, etc. — 13 keys) localized in EN / RU / DE / FR / ES.

### Fixed

- **Hot-reload after admin "Save & Connect" for NOWPayments**: panel was instantiating the legacy `CryptoPaymentProvider` (without `verify_signature()`), so the next IPN crashed the webhook handler. Now uses the same `NOWPaymentsProvider` class as the boot path.
- **Audit log %-formatting** — `loguru.logger.warning("…actor=%s", x)` printed literal `%s` placeholders. Switched to f-strings.

---

## v1.5.42 — 2026-05-04

Comprehensive audit + hardening of the entire payment pipeline. Closes a row of silent vulnerabilities and makes "customer paid but subscription didn't activate" essentially impossible.

### Security

- **Signature verification for every webhook**, with no exceptions:
  - NOWPayments: HMAC-SHA512 over sorted JSON (`x-nowpayments-sig`).
  - Stripe: official `stripe.Webhook.construct_event(body, sig_header, secret)` with timestamp tolerance.
  - Razorpay: HMAC-SHA256 over raw body (`X-Razorpay-Signature`).
  - Payme: HTTP Basic auth with constant-time secret compare.
  - CryptoPay: HMAC-SHA256, key = SHA256(api_token).
  - PayPal: production verification via PayPal's `/v1/notifications/verify-webhook-signature` API.
  - Mollie: validation by API call-back (per Mollie's design).
- Bad signature now returns `HTTP 401 Webhook signature invalid`. Previously several providers accepted unsigned bodies and credited free subscriptions.
- New PayPal **Webhook ID** field in `Settings → Payment Providers`. Without it, production PayPal webhooks couldn't be verified at all.

### Reliability

- **Dropped-webhook recovery poller**: every 60 seconds the monitoring loop walks pending payments older than 15 seconds and asks each provider's `check_payment()` directly. Self-heals lost or delayed webhooks. Idempotent (`SELECT … FOR UPDATE` plus a status re-check inside the row lock), so a delayed webhook arriving later cannot double-credit.
- **Per-invoice `ipn_callback_url` for NOWPayments**: lets one API key serve multiple front-ends safely (e.g. license sales + customer VPN on different boxes).
- Stuck-status handling: `partially_paid`, `expired`, `refunded` now explicitly mapped to `FAILED` instead of silently sitting in `PENDING` forever.

### Admin UX

- **`Test` button per provider** runs an offline self-check: provider loaded, API ping (where supported), valid signature accepted, forged signature rejected, order ID extracted from test payload. Inline green/red checklist under each card.
- **Webhook URL surface** — every provider card now shows the exact URL to register on the provider's dashboard (auto-built from `CLIENT_PORTAL_DOMAIN`) plus a one-click Copy button and a hint listing the required events to subscribe to.
- New `RAZORPAY_WEBHOOK_SECRET` field in admin (was previously settable via `.env` only).

### Documentation

- New `payment-setup.md` covering all 7 providers (NOWPayments, CryptoPay, PayPal, Stripe, Mollie, Razorpay, Payme) — required fields, dashboard URLs, sandbox vs production, troubleshooting.
- New `webhook-security.md` — full pipeline diagram, signature schemes per provider, idempotency story, recovery loop.

### Free-tier gating

- The list of payment providers visible to customers is hard-filtered on the API: a free-tier instance shows **only NOWPayments**. Stripe / PayPal / Mollie / Razorpay / Payme / CryptoPay become visible only on paid licenses. Backend rejects forged provider IDs with `HTTP 403`.
- The Billing page on free tier no longer shows a misleading "Add another method" button; instead an explicit upsell card with a link to the upgrade flow.

---

## v1.5.34 — 2026-05-04

Complete redesign of the **Client Portal** — what your end-users see when they log in.

### Added

- **New design system** — indigo accent ramp, light + dark themes (saved per user, picked up from system preference on first visit), tokens for radius, density, typography. Inter Tight + JetBrains Mono webfonts.
- **New shell**: 60 px header with brand logo, 5-item nav (Dashboard / Plans / Billing / Corp VPN / Support), theme toggle, notifications, language pill (EN/RU/DE/FR/ES), avatar, sign-out. Footer with auth-gated GitHub promo.
- **Real traffic chart** on the dashboard, served by a new `GET /client-portal/dashboard/traffic-series?range=7d|14d|30d|all` endpoint that aggregates the existing `traffic_daily` snapshots. Dual area chart (download = accent, upload = info-cyan), trend % vs the previous period, summary number, segmented tabs.
- **Sparklines** on stat cards: green decreasing line on "Days remaining" (synthesised client-side), indigo line on "Active devices" (real `active_devices_series` from the API).
- **Connection status banner** with pulsing orb (success / warn / off), real device data only — server name, protocol, IPv4. No fabricated metrics.
- **Working Billing page**: real provider list, mobile-friendly grid history, "Add another method" opens the same chooser used at signup. Empty state when no payment methods.
- **Corporate VPN map** with relay topology, animated dashed peer links, per-site stats, network issues banner, full diagnostics.
- **New Login + Register pages**: gradient + grid + radial blooms background, branded card with bundled `flirexa-logo.png`, password eye-toggle, remember-me check, theme toggle floating top-right, meta links below the card.
- **Mobile UX**: burger drawer with scrim instead of bottom-bar, sticky header (worked around an iOS-Safari `overflow-x: hidden` quirk), 16-px input font on auth pages to prevent iOS focus-zoom, 4 → 2 → 1 grid breakpoints for stats, table → stacked card layout for payment history on phones.
- Full localisation: EN / RU / DE / FR / ES.

### Fixed

- Sticky header was breaking on mobile because legacy `html { overflow-x: hidden }` and `body { overflow-x: hidden }` created a scrolling-context that ate `position: sticky`. Replaced with `overflow-x: clip` (modern browsers) — sticky restored.
- Logout, notifications, language pill restored on the mobile header (the `≤860px` nav rule was hiding too much). Avatar dropped instead since it's decorative.
- `TrafficChart` and `Sparkline` use only CSS variables — palette switches with theme without re-render.

---

## v1.5.10 — 2026-05-03

Foundational pieces that the new client portal needed.

### Added

- New `traffic_daily` aggregation endpoint (`GET /client-portal/dashboard/traffic-series`) — returns per-day rx/tx aggregated across the user's clients, plus an `active_devices_series` (distinct clients with non-zero traffic per day) and a `summary` with totals + trend % vs previous period. Used by the new dashboard chart and sparklines.
- Auto-apply updates feature: instances on the test or stable channel can opt in to automatically apply new versions via the monitoring loop. 24-hour cooldown after any failure. Toggle in `Settings → Updates`.
- Multi-agent support — a single host can now run several VPN agent processes side-by-side (e.g. WireGuard + AmneziaWG on the same box), each on a unique systemd unit and HTTP port.
- "Install AmneziaWG" button alongside "Install Proxy" on the server detail page, with auto-pick of free `awgN` interface name, listen port and `/24` address pool, plus a two-tier install path (official PPA first, fallback to our `flirexa.biz/mirror/amnezia/<series>/` mirror if the PPA is unreachable from the host).
- Cancel button (AbortController) for long-running install flows — Install Proxy / Install AmneziaWG.

### Fixed

- Updates page: the "Update failed" flash that briefly appeared on every successful update — replaced the loose status filter with an explicit `ACTIVE_STATUSES` / `TERMINAL_STATUSES` allowlist, plus polling re-arms unconditionally on every loadStatus tick.
- Updates page: "Current Version" pill stayed empty until the user clicked "Check for updates" — added unconditional `/updates/check` fallback on mount, retry-with-backoff (1 s → 2 s → 4 s → 8 s), periodic 60 s refresh, and `visibilitychange` re-fetch.
- Updates page: "Update in progress" sometimes hung forever after the actual update finished — drain stuck progress whenever `loadStatus` reports no `active_update_id`.
- ROLLBACK_REQUIRED stuck flag: if an earlier update transitioned to `ROLLBACK_REQUIRED` and a later update succeeded, the old flag was leaving the system in `update_in_progress` mode forever (and 423-blocking writes). Reconcile pass now auto-clears.
- Subscription's `traffic_used_total_gb` was crashing with `TypeError: NoneType + NoneType` when `rx`/`tx` were nullable on the row. Made None-safe and added migration `029_backfill_subscription_traffic.py`.
- AmneziaWG installs failed in several distinct ways across different environments. Reworked `agent_bootstrap.py`:
  - Per-interface service name `vpnmanager-agent-{interface}.service`.
  - Auto-pick free port 8001-8099 (scans listening ports + sibling agent unit ports).
  - `bash -c '...'` wrapping so word-splitting works under zsh too.
  - `Acquire::ForceIPv4=true` apt flags for hosts with broken IPv6.
  - Three retries on `apt-get update` with 5 s backoff.
  - Multi-firewall S7 step (ufw + iptables + nftables — important on hosts with default-deny chains).
  - S4.6 step opens the WG/AWG listen UDP port in all three firewalls.
  - External `/health` probe in S8 catches the firewall-blocked-but-running case.
  - Uninstall accepts `service_name` + `interface_hint` so it removes the right unit + config.
- Plus auto-pick free `/24` address pool when default `10.66.66/24` is taken on the remote (probes via `ip -o -4 addr` over SSH).

---

## v1.5.4 — 2026-05-02

A short follow-up bundling a few UX requests and one update-bookkeeping fix.

### Added

- **Logout button in the user menu.** Top-right user-circle icon opens a menu with a clear Logout action that clears tokens and returns you to `/login`. Localized in 5 languages.
- **Calendar date picker for client expiry.** The Clients form now lets you pick an exact expiry date alongside the existing day-count buttons (7 / 30 / 90). Useful when you need to align expiry with a specific calendar date.
- **IPv4-only toggle per VPN server.** New checkbox in the server create form: when enabled, generated client configs strip the IPv6 `Address` line. Useful where IPv6 isn't fully tunneled and could leak DNS, or where the upstream provider doesn't route IPv6.

### Fixed

- **Mobile: AmneziaWG client config no longer overlaps two QR codes.** On narrow screens the WireGuard QR and the AmneziaVPN share-link QR now stack instead of squeezing into the same row.
- **No more spurious "business_mutation blocked in update_in_progress" errors.** If an earlier update transitioned to `ROLLBACK_REQUIRED` because the post-update health check timed out, and a later update then succeeded, the system was leaving the old `ROLLBACK_REQUIRED` flag behind. The operational-mode middleware kept treating the box as "update in progress" and 423-blocked every write — including creating new clients. The reconcile pass now auto-clears stale `ROLLBACK_REQUIRED` rows once a later `SUCCESS` row exists for the same instance.
- **Update badge now flashes promptly without manual "Check for updates".** `_CACHE_TTL` reduced from 1 hour to 60 seconds so the navbar's per-minute poll actually picks up newly published manifests.
- **Top-level `navbar.logout` translation key.** Was previously only defined inside `cp.nav.logout` (client portal namespace), so the admin Navbar showed the literal `navbar.logout` string. Added in en/ru/es/fr/de.

---

## v1.5.0 — 2026-05-01

A UX milestone bundling everything from 1.4.96 → 1.5.0 stable:

### Added

- **Online / Offline filter for clients.** The status dropdown on the Clients page now has explicit Online and Offline options (handshake within last 3 minutes counts as online). Localized in 5 languages.

### Fixed

- **Update progress no longer shows a brief "✗ Update failed" before "✓ Update completed successfully".** The reconcile pass that runs at API startup used to prematurely flip the in-flight record to FAILED with `Server restarted during update — outcome unknown` if it ran before the detached `update_apply.sh` had time to write its `apply.exitcode`. With a 120-second grace window the record now stays APPLYING during the typical restart, and the panel renders a clean in-progress card all the way to success.
- **Heartbeat / online-validator / auto-update-check / update-checker logs now actually show up in `journalctl`.** They were running correctly but their startup banners and runtime messages were silently dropped under uvicorn's logging override. Switched these modules to use `loguru` directly. Side benefit: the noisy "Loaded cached license status: ok" line is now DEBUG instead of INFO.
- **Navbar's "update available" badge refreshes promptly.** Was polling every 30 minutes; now polls every 60 seconds, plus on tab focus, plus on every admin-panel route change. `/updates/status` is server-side cached so the cadence is cheap.

### Changed

- **License server stays dormant on un-activated FREE installs.** No heartbeat, no validation calls, no telemetry whatsoever — the entire license-server interaction surface is opt-in. Activation (via `install.sh` with a code, or Settings → License → Activate / Re-fetch) wakes everything up automatically on the next iteration.
- **Admin-panel UI polished end-to-end.** The cheap inline emoji icons (💾 🤖 👥 ✓ ✗ 🔍 ⚠️ 🔄 ⭐ 🗑 ✏️ 🔒 🚀 ⚙️ 💎 🌐 …) across Updates, Servers, Clients, Settings, SystemHealth, Backup, Applications, SupportMessages, AppLogs, PortalUsers, Bots, ServerMonitoring, FeatureLockedCard, plus payment-provider cards in Settings — replaced with Material Design Icons rendered as `<i class="mdi mdi-…">` SVG, matching the sidebar style. HTML-entity icons (`&#x267E;`, `&#x23F8;`, `&#x25B6;`, …) cleaned up too.

---

## v1.4.95 — 2026-05-01

### Fixed

- **Heartbeat / license validator / auto-update-check loops now actually log to journalctl.** They were all running correctly under the hood, but their startup banners and runtime messages were silently dropped because the `logging` → `loguru` bridge gets overridden by uvicorn after API startup. Switched these modules to use `loguru` directly. You'll now see lines like `Auto update-check started (interval=21600s)`, `Instance heartbeat started (interval: 300s)`, and `Online license check via https://flirexa.biz: status=ok tier=enterprise` in `journalctl -u vpnmanager-api`.
- **Reduced log noise.** "Loaded cached license status: ok" was emitting at INFO level on every status-collector tick (every panel poll). Demoted to DEBUG.

---

## v1.4.92 — 2026-05-01

### Changed

- **License server stays dormant on un-activated FREE installs.** The instance heartbeat now skips its iteration when `LICENSE_KEY` is empty — no calls to the license server, no telemetry of any kind for boxes that never went through activation. Pairs with the existing online-validator behavior, so the entire license-server interaction surface is now strictly opt-in. The validator + heartbeat wake up automatically the moment an activation code is entered (via `install.sh` or Settings → License).

### Why

Previous behavior was "validator + heartbeat always run, but skip if no key". That still leaked a `LICENSE_KEY=""`-flagged heartbeat on every interval. Now the heartbeat doesn't fire at all unless there's a key to send. FREE-tier installs are now genuinely silent.

---

## v1.4.91 — 2026-05-01

### Added

- **Auto-poll for new versions in the background.** A periodic check (default every 6 hours, controlled by `UPDATE_CHECK_INTERVAL`) refreshes the manifest cache. The admin panel's navbar now shows a small package-up icon with a red dot when a newer version is available — click it to jump to Updates. No auto-apply: you stay in control of when to install.
- **`publish_update.py --to-both` flag** for vendors operating primary + backup license servers. One command publishes / promotes / lists / deletes across both, surfacing per-server failures at the end without aborting halfway. Both URLs are configurable via env (`UPDATE_SERVER_URL`, `UPDATE_SERVER_BACKUP_URL`).

### Fixed

- **VPN interfaces no longer dropped during update.** `update_apply.sh` now snapshots active `wg` and `awg` interfaces before stopping services and restores any that didn't come back up. Previously, manually-started or orphan interfaces (e.g. an `awg-quick@awg1` that was never `systemctl enabled`) could disappear after a service restart cycle. Real customers' connections survive untouched now.
- **`vpnmanager license status` now reads the right `.env`.** In release-layout installs (`/opt/vpnmanager/releases/<ver>/`) the CLI was looking for `.env` next to the source, but the persistent `.env` lives at the install root one level up. Symptom: CLI reported `not_activated` while the API correctly showed an active enterprise license. CLI now walks up the directory tree to find `.env`.

---

## v1.4.89-1.4.90 — 2026-05-01

### Added

- **"Re-fetch License" button in Settings → License.** Pairs with the activation replay endpoint (1.4.88). If your license key was lost during the original activation (network blip, lost terminal, parsing error) you can now re-enter your activation code from the panel and recover the same key. Hardware-bound — only works from the original install. No support ticket needed.
- **Translations** for the Re-fetch UI in English, Russian, Spanish, French, German.

---

## v1.4.88 — 2026-05-01

### Added

- **Activation replay endpoint** (`POST /api/activate/replay`) on the license server. Re-issues the original signed license payload (same plan, expiry, hardware binding) with a fresh signature, for the recovery case where `/api/activate` succeeded but the key didn't land in `.env`. Per-code rate limit: 3 attempts per 24 hours. Hardware mismatch returns 403.

### Fixed

- **`install.sh` activation prompt now works under `curl … | bash`.** The headline install command (`curl -fsSL https://flirexa.biz/install.sh | bash`) silently skipped the prompt because bash's stdin was the curl pipe. Paid customers couldn't enter their activation code that way unless they pre-set `SB_ACTIVATION_CODE`. The prompt now reads from `/dev/tty` explicitly. Empty input, `n`, `no`, `free`, or `skip` selects FREE; anything else is treated as an activation code.

---

## v1.4.87 — 2026-04-30

### Fixed

- **`vpnmanager` CLI wrapper finds the venv in release-layout installs.** After resolving the symlink chain to `/opt/vpnmanager/releases/<ver>/vpnmanager`, the wrapper expected `venv/` next to the script, but venv lives at `/opt/vpnmanager/venv` (parallel to `releases/`). Falling back to system `python3` produced `ModuleNotFoundError: No module named 'dotenv'`. The wrapper now walks up from script dir up to 3 levels looking for `venv/bin/python3`.

---

## v1.4.86 — 2026-04-30

### Fixed

- **Bot services stop looping when the token is missing or `*_BOT_ENABLED=false`.** Previously, `vpnmanager-admin-bot` and `vpnmanager-client-bot` would crash-loop several hundred times per hour — admin-bot exited with status=1 on missing token, client-bot exited cleanly but the unit had `Restart=always` so systemd restarted it anyway. The bots now `sys.exit(0)` cleanly on missing/disabled config, and the units use `Restart=on-failure` — no restart cycle, no CPU waste, no journal spam.

---

## v1.4.85 — 2026-04-30

### Added

- **Dual-format QR code for AmneziaWG clients.** The client view now shows two QRs side by side: a plain `.conf` for the AmneziaWG simple app, and a `vpn://` share URL for the AmneziaVPN mobile app. Same peer, different formats — pick whichever matches your client.
- **Trial vs paid grace period.** Short licenses (≤14 days, e.g. trials) now have no grace period — when they expire, the system goes degraded immediately. Paid licenses keep the standard 72-hour grace window for offline clock skew.

### Fixed

- **License server URL defaults to `https://flirexa.biz`** in fresh builds (was `example.com` placeholder). Operators running self-hosted license servers still override via `.env`.

---

## v1.4.70 — 2026-04-29

### Fixed

- **AmneziaWG server wouldn't start ("Failed to start server" / 500)** — four stacked issues, all hit on a fresh FREE install once you actually try to bring an AmneziaWG interface up alongside the auto-provisioned WireGuard:
  1. **Wrong config path.** apt-installed `awg-quick` from `ppa:amnezia/ppa` looks for the config at `/etc/amnezia/amneziawg/<iface>.conf` (note the extra `amnezia/` segment), not `/etc/amneziawg/<iface>.conf`. The codebase wrote everywhere to the latter so awg-quick reported "config does not exist". Replaced `/etc/amneziawg` → `/etc/amnezia/amneziawg` across `servers.py`, `server_manager.py`, `agent_bootstrap.py`, `backup_manager.py`, and the `AmneziaWGManager` constructor default.
  2. **Config file was never written.** `start_server()` called `wg.start_interface()` directly without writing the config to disk. WireGuard got away with it because `install.sh` writes `/etc/wireguard/wg0.conf` eagerly, but the user-created AmneziaWG only had a DB record. `start_server()` now calls `save_server_config()` first; cheap, idempotent, and picks up new peers since last start.
  3. **Parent dir missing.** `write_config_file()` opened the file directly, which fails on a fresh install where `/etc/amnezia/amneziawg/` doesn't exist yet. Added an `os.makedirs(parent, exist_ok=True)` before write.
  4. **PostUp/PostDown was malformed for dual-stack address.** AmneziaWG's `generate_server_config()` derived the IPv4 subnet by splitting the full address on `/`, but the address comes in as `10.66.66.1/24,fd42:42:42::1/64` (combined IPv4+IPv6). The naive split produced `10.66.66.1/24,fd42:42:42:.0/64`, which both `iptables` and `ip route` rejected, so `awg-quick` rolled back the interface. Now we extract the IPv4 half before parsing.
  5. **Port collision.** AmneziaWG defaulted to listen_port 51820 — same as the auto-provisioned WireGuard — so the kernel rejected the second bind with `RTNETLINK answers: Address already in use`. Local server creation now scans existing ports and walks up from the requested one until it finds a free slot. The drift is logged.

End-to-end verified on a clean VM: install → activate FREE → keep auto-WireGuard → create AmneziaWG → click Start → `awg show` lists the interface with all obfuscation parameters and traffic flows.

### Earlier 1.4.68 / 1.4.69 commits land in this release together; bumping straight to 1.4.70 since none of the intermediates were promoted to stable individually.

---

## v1.4.67 — 2026-04-29

### Fixed

- **Update + license server URL defaults pointed at `https://example.com`.** Fresh installs that didn't explicitly set `UPDATE_SERVER_URL` / `LICENSE_SERVER_URL` in `.env` got `404 No manifest found for channel 'stable'` on update checks and trial registration silently failed. Default to `https://flirexa.biz` (operators running their own license server still override via `.env`).

---

## v1.4.66 — 2026-04-29

### Changed

- **FREE tier server limit is now per-protocol, not total.** Previously the cap was "one server" — with the auto-provisioned WireGuard taking that slot, FREE users couldn't add AmneziaWG without first deleting their working WireGuard. The intent has always been *both* protocols on FREE (DPI-resistance is core value), so the cap moves to "one of each protocol type":
  - FREE: up to 1 WireGuard + 1 AmneziaWG = 2 servers total.
  - Starter (`$19/mo`): adds Hysteria2 + TUIC = up to 4 servers (one of each).
  - Business+ keeps the existing `multi_server` feature, which lifts the cap fully (10 / unlimited).
- Server-create endpoint now counts servers of the same `server_type` instead of all servers. The pg advisory lock is preserved so concurrent requests can't both win.
- Local `LICENSE_TIERS` fallback: `FREE` 1 → 2, `STANDARD` 1 → 4.

---

## v1.4.65 — 2026-04-29

### Fixed

- **Fresh installs were missing AmneziaWG userspace tools.** 1.4.64 unblocked AmneziaWG creation at the license layer, but `install.sh` only ever installed `wireguard-tools` — so on a fresh VPS, creating an AmneziaWG server failed with a `500 Internal Server Error` (`FileNotFoundError: 'awg'`). Existing installs that had been hand-configured (e.g. the maintainer's own production box) worked fine, which masked the bug for everyone but new users.
- Installer now adds the `amnezia/ppa` apt repository and installs `amneziawg`, `amneziawg-tools`, and `amneziawg-dkms` (with the running kernel headers) right after the core package step. The whole AmneziaWG block is best-effort — if the DKMS module fails to compile on a stripped VPS image with no headers, the install still completes and the panel still works in WireGuard-only mode, with a clear log warning.
- Runtime: `core/amneziawg.py` wraps the `awg` subprocess calls; a missing binary now raises a `RuntimeError` carrying the exact apt command to fix it, and the create-server endpoint surfaces that as `400 Bad Request` instead of leaking a generic 500.

---

## v1.4.64 — 2026-04-29

### Fixed

- **AmneziaWG was incorrectly gated as a paid feature.** The server-create endpoint mapped `amneziawg` → license-feature `amneziawg`, which doesn't exist on FREE-tier signed licenses, so any FREE user trying to provision an AmneziaWG server got `403 "AMNEZIAWG protocol requires the 'amneziawg' feature. Upgrade your plan to enable it."` This contradicts both the README and `docs/free-vs-paid.md`, which list AmneziaWG as a core FREE feature — it's the DPI-resistant protocol that makes the product useful on hostile networks.
  - Real impact for FREE users: a fresh install auto-provisions a WireGuard server. Anyone who wanted AmneziaWG instead had to delete the auto-server and create a new one — and the second create was blocked. They were stuck on WireGuard. Now AmneziaWG creation just works.
  - Hysteria2 / TUIC still require the `proxy_protocols` feature (Starter+), unchanged.

---

## v1.4.63 — 2026-04-28

### Security / Fixed

- **License feature gate for traffic-rules was a no-op on FREE installs.** The middleware checked `/api/v1/traffic-rules` but the router is registered at `/api/v1/traffic`, so the `startswith` match never fired and FREE-tier users could call `GET /api/v1/traffic/top`, `/api/v1/traffic/rules`, `/api/v1/traffic/clients` without paying. POST/PUT had inline checks, but DELETE was also open. Confirmed on a FREE VM (license features = wireguard/client_portal/telegram_bots only) — all three endpoints returned 200 before, 403 after. The two prefixes (router and middleware) must match exactly; we added a comment so it doesn't drift again.
- **`LICENSE_CHECK_ENABLED=false` used to silently short-circuit the entire license middleware** — no log, no warning. A typo or a leaked .env could disable activation, expiry, online-validation, *and* feature gating without any signal. Now logs `EVENT:LICENSE_BYPASS` (rate-limited to once per 5 minutes per process) every time the bypass is hit, with an explicit "fix the env file IMMEDIATELY" hint for production.

### Fixed

- **`update_apply.sh` left `$INSTALL_DIR/VERSION` stale in release-layout mode.** Only `$CURRENT_LINK/VERSION` moved when the symlink switched. External monitoring / scripts that read `/opt/vpnmanager/VERSION` (or `/opt/vpnmanager/VERSION`) saw the previous version forever after the upgrade. Now we write `$TARGET_VERSION` to the install-root file too. Existing installs catch up on the next upgrade.

### Public mirror (`Flirexa/flirexa`) cleanup

- CI workflow was failing on every push: pytest job didn't install runtime requirements (psutil / python-dotenv / aiocryptopay → `ModuleNotFoundError`) and secrets-scan used an invalid `--base-path` flag. Both fixed; CI green again.
- Replaced remaining `vpnmanager` / `Flirexa` strings with `Flirexa` in the public mirror: `alembic/env.py` default DSN, `.env.example` header, `backup_manager.py` docstring + version stamp.

---

## v1.4.62 — 2026-04-28

### Fixed
- **Plugin URLs returned 404** — generic plugin loader ran in lifespan, which appended plugin routers to `app.routes` *after* the SPA catch-all `GET /{full_path:path}` registered in `create_app()`. FastAPI matches routes in order, so the catch-all swallowed every plugin URL with 404. Loader now runs in `create_app()` right before the SPA mount, so plugin routes win the match. End-to-end verified on a fresh VM install with the `monthly-revenue` demo plugin: install-by-URL → restart → `GET /api/v1/plugins/monthly-revenue/current` returns 200.
- **Loader did not honor `community` feature flag** — manifests declaring `requires_license_feature: "community"` were skipped on FREE installs because the loader required *every* declared feature to be granted by the license. The reserved name `community` is now treated as always-granted, matching what the docs already describe and letting third-party community plugins load on every tier.
- **`curl https://flirexa.biz/install.sh | sudo bash` aborted on non-TTY shells** — the installer started with a bare `clear` under `set -e`, which exits non-zero when `TERM` is unset/unknown (common when piping through SSH or CI). Made `clear` best-effort (`clear 2>/dev/null || true`) so the banner step never kills the install.

---

## v1.4.61 — 2026-04-28

### Added
- **Plugin marketplace (variant 1) — install-by-URL** in admin panel. New endpoints: `GET /api/v1/plugins/installed`, `POST /api/v1/plugins/install` (URL + SHA-256), `DELETE /api/v1/plugins/{name}`. Tarball must contain a single top-level dir matching `manifest.json.name`; max 25 MB; SHA-256 verified before extraction. Restart required to pick up newly-installed routes. Vue admin page lists installed plugins (core vs user-installed) and provides the install / uninstall UI.

### Changed
- **Donate button** moved to leftmost slot of the right-side toolbar group, redesigned as a text+heart pill instead of an icon-only button.
- **Docs**: removed Russia-specific brand examples (Yandex etc.) from `free-vs-paid.md` and adjacent pages; replaced with international equivalents.

---

## v1.4.60 — 2026-04-27

### Added
- **Donate button + reminder modal in admin panel** — heart-icon button always visible in topbar; opens a modal with a "Support on GitHub" CTA linking to the project's crypto donation addresses (BTC / ETH / USDT TRC-20 / USDT ERC-20). The modal auto-shows on first install, then re-shows only after a 7-day cooldown after the user dismisses it. The free tier stays free; donations fund the work, they do not unlock features. Localised across EN / RU / DE / FR / ES.

### Changed
- **Starter tier client cap 500 → 300** in the offline LICENSE_TIERS fallback. Aligns with the new pricing copy on flirexa.biz. Existing customers are unaffected — the cap they get is whatever was in their signed payload, refreshed via /api/validate.

### Notes
- v1.4.59 was published to the test channel, then superseded by v1.4.60 (same changes, plus a contrast fix for the donate modal text). Only v1.4.60 reached stable.

---


## v1.4.43 — 2026-04-17

### Fixed
- **QR code crash on Cyrillic client names** — `_safe_filename()` used `\w` which matches Unicode; replaced with explicit `[a-zA-Z0-9_\-.]` to ensure ASCII-only Content-Disposition headers

---

## v1.4.42 — 2026-04-12

### Added
- **Server display names** — admins can rename servers so clients see friendly names instead of real IPs in the client portal
- **Sortable columns** in Clients table — click any header (name, server, IP, status, traffic, bandwidth, expiry) to sort asc/desc with arrow indicator
- **System Health mode indicator** — banner shows "7/7 OK (Quick)" vs "10/10 OK (Full)" with clickable hint to switch modes
- **Concurrent instance detection** — real-time clone detection within 10-minute window (no IP requirement — catches clones behind same NAT)
- **Clone rejection at validation** — `/api/validate` blocks concurrent instances immediately instead of waiting 7 days
- **Hardware fingerprint hardening** — added DMI UUID, disk serial, RAM size to hardware binding (7 entropy sources total)
- `INTERNAL_LICENSE_MODE` now requires `.dev-mode` marker file (not just env var)
- `install.sh`: license server URL configurable via `SB_LICENSE_SERVER_URL` env var
- `install.sh`: improved network interface detection with multiple fallback methods

### Fixed
- **Backup page white screen** — `$t()` used in `<script setup>` without `useI18n()` import, causing ReferenceError crash
- **Settings page crash** — missing i18n keys (`systemTools`, `limitCheck`, etc.) caused partial render failure
- **Proxy client creation failure** — `CreateClientResponse.ipv4` was non-Optional, proxy clients with `ipv4=None` crashed Pydantic validation
- **Proxy config rollback** — `_apply_proxy_config()` result was silently ignored; client saved to DB even when SSH config application failed
- **Unicode crash on QR/config download** — Cyrillic client names caused `UnicodeEncodeError` in Content-Disposition headers
- **Hysteria2/TUIC configs use domain** — client configs now use domain as connection host when TLS cert exists (not IP), fixing TLS handshake failures
- **`portalUsers.never`** i18n key added — was showing raw key string instead of "Никогда"
- `datetime.utcnow()` deprecated calls replaced with `datetime.now(timezone.utc)`
- Rate limit cleanup threshold lowered from 10000 to 1000 IPs
- Bare `except Exception` narrowed to specific types in `_deserialize_permissions()`
- Cross-worker proxy config lock via `pg_advisory_xact_lock`

### Changed
- **Client Portal Dashboard** — UI polish: hero KPI card, subscription details in 2 groups, device list restructured, referral inline copy, mobile responsive
- **Server Monitoring** — complete visual overhaul: 3-level hierarchy (name+status → message → metrics), prominent colored status badges, metrics in CSS grid, actions as fixed-size buttons
- **System Health** — compact banner, quiet status badges when healthy, metrics as plain text (not pills), progress bars thicker (6px)
- **Portal Users table** — zebra rows, username/email hierarchy, tier color badges, filters unified bar with search icon, "Never" for empty last login
- **Subscriptions table** — tier color badges (not red `<code>`), ∞→"Unlim." text, delete button hidden until hover, modal restructured into 5 grouped sections
- **Settings page** — 12 new i18n keys, ~25 hardcoded strings replaced with `$t()`, branding section fully localized
- **Admin panel** — complete i18n for Settings, missing keys added to all 5 locales (en/ru/de/es/fr)
- Removed 109 unnecessary `|| 'fallback'` i18n patterns from client portal
- Removed "vpnmanager" from client-facing error messages

---

## v1.4.11 — 2026-04-07

### Added
- `hostname` and `version` fields in every JSON log entry — makes multi-instance log aggregation and version-correlated debugging straightforward
- `GET /api/v1/system/app-logs/errors` — dedicated errors-only endpoint (shortcut for `?errors_only=true`)
- `errors_only` query parameter on `GET /api/v1/system/app-logs`
- **App Logs** admin UI page (`/app-logs`): component tabs (API / Worker / Agent), All / Errors filter, table with time / level / req\_id / method / path / status / ms / message columns, click-to-expand error rows
- `systemApi.getAppLogs()` and `getAppLogsErrors()` added to frontend API client
- Operational event markers for grep-friendly monitoring: `EVENT:API_START/STOP`, `EVENT:WORKER_START/STOP`, `EVENT:BOOTSTRAP_SUCCESS/FAILURE`, `EVENT:UPDATE_START/SUCCESS/FAILURE`, `EVENT:ROLLBACK_START/SUCCESS/FAILURE`, `EVENT:BACKUP_SUCCESS`, `EVENT:RESTORE_SUCCESS/PARTIAL`, `EVENT:LICENSE_BLOCKED`, `EVENT:AGENT_HEALTH_FAILURE`
- `RequestLoggerMiddleware` — single access log entry per request with method / path / status_code / duration_ms bound into loguru context so all log lines for a request share the same fields
- 26 automated tests: request_id propagation, JSON structure validity, hostname/version fields, truncation, empty/broken log file, errors_only filter, secrets protection

### Changed
- `X-Request-ID` header now generated by dedicated middleware (replaces inline lambda); custom header value from caller is honoured and echoed back
- `nav.logs` label changed to "Audit Logs" to distinguish from the new App Logs page

---

## v1.4.6 — 2026-04-05

### Added
- Structured JSON logging across API, worker and agent components: every log line is a JSON object with `timestamp`, `level`, `component`, `message`
- `request_id` propagation — `X-Request-ID` header is assigned per request and bound into every log entry produced during that request via loguru `contextualize()`
- HTTP access log fields in each entry: `method`, `path`, `status_code`, `duration_ms`
- Log size protection: message body capped at 10 KB, error strings capped at 2 KB (both truncated with `[truncated]` marker)
- `GET /api/v1/system/app-logs?component=api|worker|agent&lines=N&errors_only=bool` — tail of structured application logs
- `GET /api/v1/system/app-logs/errors?component=...&lines=N` — errors-only shortcut
- Operational event markers (`EVENT:*`) in log messages for grep-friendly monitoring: `EVENT:API_START`, `EVENT:API_STOP`, `EVENT:WORKER_START`, `EVENT:WORKER_STOP`, `EVENT:BOOTSTRAP_SUCCESS`, `EVENT:BOOTSTRAP_FAILURE`, `EVENT:UPDATE_START`, `EVENT:UPDATE_SUCCESS`, `EVENT:UPDATE_FAILURE`, `EVENT:ROLLBACK_START`, `EVENT:ROLLBACK_SUCCESS`, `EVENT:ROLLBACK_FAILURE`, `EVENT:BACKUP_SUCCESS`, `EVENT:RESTORE_SUCCESS`, `EVENT:RESTORE_PARTIAL`, `EVENT:AGENT_HEALTH_FAILURE`, `EVENT:LICENSE_BLOCKED`
- **App Logs** page in admin panel (`/app-logs`) — component tabs (API / Worker / Agent), All / Errors filter, table with all JSON fields, expandable error rows
- 26 automated tests covering request_id propagation, log endpoints, JSON structure, truncation, secrets protection

### Changed
- Logrotate config at `/etc/logrotate.d/vpnmanager` — daily rotation, 30-day retention, `copytruncate` (no process restart needed)

---

## v1.2.72 — 2026-03-26

### Added
- Business invariant validator: 7 automated checks run every 30 minutes — detects expired clients with active access, completed payments without subscriptions, proxy clients with fake bandwidth limits, and more; auto-fixes violations
- Self-healing state reconciler: ghost peer detection — if a client is disabled in DB but the WireGuard peer still exists on the server, it is automatically removed (access leak prevention)
- Payment pipeline tracing: every payment now has a `trace_id` and a `pipeline_log` recording each step (create → webhook → activate → sync_wg); inconsistent payments are flagged for admin review
- Fail-safe mode: when the system detects critical conditions (invalid license, all WG servers unreachable), new payments are blocked with a clear error message instead of creating broken state
- Worker heartbeat: background worker writes a heartbeat to DB every cycle; health endpoint detects stale/dead worker
- `GET /api/v1/health/full` — comprehensive real-state health check: database, WG servers, license, worker, business invariants → returns OK / DEGRADED / FAIL with problem list
- `GET /api/v1/system/metrics` — operational counters: active clients, expired+enabled (critical flag), payment stats, subscription counts, server drift count
- `GET/POST /api/v1/system/failsafe` — view and manually control fail-safe mode
- Daily health report at 08:00 UTC via Telegram admin notification

### Fixed
- Silent failures in payment and subscription pipeline replaced with structured logging (trace_id, user_id, step name)
- `state_reconciler`: previously only re-added missing peers; now also removes peers that are disabled in DB but still live on the WireGuard interface

### Changed
- `client_portal_payments` table: added `trace_id`, `pipeline_log`, `pipeline_status` columns (migration 016)

---

## v1.2.71 — 2026-03-25

### Fixed
- Proxy clients: traffic and bandwidth columns in Clients table now show `—` instead of fake values
- TC bandwidth limits now enforced immediately after subscription change (not only at next worker cycle)
- `_sync_wg_after_payment` fallback when admin API is not configured — now applies limits directly via DB
- `check_expired_clients`: added SELECT FOR UPDATE (skip locked) to prevent duplicate processing under concurrent worker runs
- Client disabling: DB always updated even if WireGuard peer removal fails
- Duplicate pending payments: old pending payments for the same user/tier are cancelled before creating a new one
- Thread-safe traffic cache reads and writes via `_TRAFFIC_CACHE_LOCK`
- Per-client try/except in `_disable_user_clients` — one failed client no longer blocks the rest
- `is_proxy_client` criterion strengthened: based solely on `public_key is None`

---

## v1.2.46 — 2026-03-24

### Fixed
- White screen when clicking WebAccess radio buttons in Settings — caused by unescaped `@` symbols in vue-i18n locale strings (`admin@example.com`, `@CryptoTestnetBot`) triggering "Invalid linked format" compile error at runtime

---

## v1.2.37 — 2026-03-20

### Fixed
- Missing i18n translation keys for navigation, dashboard charts, server bandwidth, and settings across all 5 locales (EN/RU/DE/ES/FR)

---

## v1.2.36 — 2026-03-20

### Added
- Corporate VPN module: site-to-site WireGuard mesh networks with visual topology map
- Relay/gateway node support for NAT traversal between offices
- Per-peer diagnostics and connection status in corporate networks
- System health monitoring dashboard (10 components: DB, API, worker, license server, WG, bots, payments, disk/mem/cpu)
- Server drift detection: auto-reconcile of DB state vs live WireGuard interface

### Improved
- AmneziaWG full support with obfuscation parameters (Jc/Jmin/Jmax/S1/S2/H1-H4)
- Vuexy UI design system across admin panel and client portal
- Payment module hardening: SELECT FOR UPDATE, atomic promo usage, IPN secret enforcement
- Multi-language support: 6 languages (EN, RU, UK, DE, FR, ES)

---

## v1.2.35 — 2026-03-10

### Added
- White-label branding: name, logo, colors configurable from admin panel
- Update mechanism with rollback support
- Backup and restore: scheduled database + config backups

### Fixed
- License validation grace period (72h offline tolerance)
- Client portal dashboard layout fixes

---

## v1.2.0 — 2026-02-15

### Added
- Plan-based licensing model (Standard / Pro / Enterprise)
- RSA-signed license keys with hardware binding
- Online license validator with heartbeat
- Client portal: user self-registration, subscription plans, crypto payments
- Telegram client bot for end-user self-service

---

## v1.1.0 — 2026-01-20

### Added
- Multi-server management via SSH and lightweight HTTP agent
- Per-client traffic counters and bandwidth limits (`tc`-based shaping)
- Promo codes, referral system, revenue analytics
- CryptoPay (NOWPayments) payment integration

---

## v1.0.0 — 2025-12-01

### Initial release
- Web admin panel (Vue 3 + Bootstrap 5)
- WireGuard server management
- Client CRUD with QR code and config export
- Telegram admin bot
- PostgreSQL backend with Alembic migrations
- Automated install script for Ubuntu/Debian
