# Changelog

All notable changes to VPN Manager are documented here.

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

Brand cleanup. The panel and client portal now ship with Flirexa branding by default — title, manifest, favicon, and OpenAPI doc title all read "Flirexa VPN Studio". The shared favicon is the bird-in-flight mark from flirexa.biz on a purple gradient, identical between admin and portal.

### Changed

- **Default app name is now "Flirexa VPN Studio"** across both frontends, the manifest.json files (PWA install name), the apple-mobile-web-app-title, and the OpenAPI `title`. The Settings → Branding override still works, so any operator who has set a custom app name will keep it.
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

- **`update_apply.sh` left `$INSTALL_DIR/VERSION` stale in release-layout mode.** Only `$CURRENT_LINK/VERSION` moved when the symlink switched. External monitoring / scripts that read `/opt/vpnmanager/VERSION` (or `/opt/spongebot/VERSION`) saw the previous version forever after the upgrade. Now we write `$TARGET_VERSION` to the install-root file too. Existing installs catch up on the next upgrade.

### Public mirror (`Flirexa/flirexa`) cleanup

- CI workflow was failing on every push: pytest job didn't install runtime requirements (psutil / python-dotenv / aiocryptopay → `ModuleNotFoundError`) and secrets-scan used an invalid `--base-path` flag. Both fixed; CI green again.
- Replaced remaining `spongebot` / `VPN Management Studio` strings with `Flirexa` in the public mirror: `alembic/env.py` default DSN, `.env.example` header, `backup_manager.py` docstring + version stamp.

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
- Removed "spongebot" from client-facing error messages

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
