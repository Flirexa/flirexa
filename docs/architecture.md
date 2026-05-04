# VPN Management Studio — Architectural Specification v1.0

**Date:** 2026-03-26 | **Based on:** v1.2.78 (`09a59ea`) | **Status:** Stage 0 — Fixation

---

## 1. System Context

### 1.1 Subsystem Map

```
┌─────────────────────────────────────────────────────────────────┐
│                        API Process                               │
│  ┌──────────┐  ┌──────────────┐  ┌─────────────────────────┐   │
│  │  FastAPI  │  │  Scheduler   │  │   License Middleware     │   │
│  │  Routes   │  │  (bg tasks)  │  │   (per-request check)   │   │
│  └────┬──────┘  └──────┬───────┘  └─────────────────────────┘   │
│       │                │                                          │
│  ┌────▼────────────────▼──────────────────────────────────────┐  │
│  │                  Service Layer                              │  │
│  │  ServerManager │ SubscriptionManager │ BackupManager  ...  │  │
│  └────────────────────────┬────────────────────────────────────┘  │
└───────────────────────────┼─────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────────┐
        ▼                   ▼                       ▼
   ┌─────────┐        ┌──────────┐           ┌────────────┐
   │PostgreSQL│        │ WG/AWG   │           │ Remote     │
   │  (DB)   │        │ (local)  │           │ Servers    │
   └─────────┘        └──────────┘           │ + Agents   │
                                             └────────────┘
```

### 1.2 Subsystem Descriptions

#### API

| | |
|---|---|
| **Responsibility** | HTTP entry point. Auth, request routing, license enforcement, rate limiting. |
| **Inputs** | HTTP requests (admin frontend, client portal, webhooks, inter-service) |
| **Outputs** | JSON responses, triggers to service layer |
| **Dependencies** | DB (SessionLocal), LicenseState (in-memory read), JWT |
| **Source of Truth** | Not a source of truth. Routes delegate to service layer. |
| **Critical Rule** | Must never directly mutate `server.status` — delegate to `_transition_status()` |

#### Worker / Scheduler (`src/api/scheduler.py`)

| | |
|---|---|
| **Responsibility** | Periodic monitoring cycle, backup cycle. Runs inside API process as asyncio tasks. |
| **Inputs** | Timer ticks, DB state |
| **Outputs** | DB mutations (subscription status, payment expiry), side-effect triggers (notifications, WG check) |
| **Dependencies** | DB, ManagementCore, SubscriptionManager, NotificationService |
| **Source of Truth** | Not a source of truth. Reads DB, writes DB. |
| **Critical Rule** | Scheduler failure must not crash API. All errors caught and logged. |

#### ServerManager / Orchestration (`src/core/server_manager.py`)

| | |
|---|---|
| **Responsibility** | Lifecycle orchestration for servers: create, delete, status transitions, check_all_limits. |
| **Inputs** | API calls, scheduler triggers |
| **Outputs** | DB mutations, SSH commands via protocol managers |
| **Dependencies** | DB, WGManager/AWGManager/Hysteria2/TUIC, BootstrapLogger, AuditLog |
| **Source of Truth** | DB is source of truth. `_transition_status()` is the single write path for `server.status`. |

#### VPN Protocol Managers (`src/core/wireguard.py`, `amneziawg.py`)

| | |
|---|---|
| **Responsibility** | Generate configs, manage WG peers, apply WG rules on local/remote server via SSH. |
| **Inputs** | Server model, Client model, DB session |
| **Outputs** | wg/awg commands, file writes on server |
| **Dependencies** | SSH (paramiko), DB |
| **Source of Truth** | DB = intended state. WG kernel interface = live state. |

#### Proxy Managers (`src/core/hysteria2.py`, `tuic.py`, `proxy_base.py`)

| | |
|---|---|
| **Responsibility** | Bootstrap, configure, and manage per-interface Hysteria2/TUIC services. Each instance owns exactly one systemd unit + one config file. |
| **Inputs** | Server model, interface name |
| **Outputs** | `/etc/hysteria/config-{iface}.yaml`, `hysteria-{iface}.service`, `purge_service()` |
| **Dependencies** | SSH (local or remote), systemd |
| **Source of Truth** | DB: `proxy_service_name`, `proxy_config_path`. Systemd: runtime state. |
| **Critical Rule** | Never share a unit or config between two proxy server instances. |

#### State Reconciler (`src/modules/state_reconciler.py`)

| | |
|---|---|
| **Responsibility** | Detect drift between DB-intended WG peer state and live WG kernel state. Auto-heal safe drift. |
| **Inputs** | DB peer list, `wg show` / `awg show` output |
| **Outputs** | `drift_detected` flag on Server, optional re-add peer via `wg set` |
| **Dependencies** | DB, WG/AWG commands (local or agent) |
| **Source of Truth** | WG kernel = live state. DB = intended state. |
| **Critical Rule** | Must skip proxy servers (`is_proxy=True`). Proxy runtime is managed by systemd, not WG. |

#### Monitoring / Health (`src/modules/health/`)

| | |
|---|---|
| **Responsibility** | Observe and report system component health and server health (peer counts, uptime, resources). |
| **Inputs** | DB, API self-check, SSH/agent queries |
| **Outputs** | Health response DTOs, cached in TTL cache (60s) |
| **Dependencies** | DB, agent `/health`, wg/awg show |
| **Source of Truth** | Health is read-only observation. Never mutates lifecycle state. |
| **Critical Rule** | Health check failure must not trigger automated lifecycle changes. |

#### Bootstrap Task Subsystem (`src/modules/bootstrap_logger.py`, `agent_bootstrap.py`)

| | |
|---|---|
| **Responsibility** | Execute and track multi-step server provisioning (S1–S8). Persist task state to DB so it survives API restarts. |
| **Inputs** | `create_task(task_id, server_id)`, bootstrap parameters |
| **Outputs** | `ServerBootstrapLog` DB record (status, logs, error, timestamps) |
| **Dependencies** | DB (`ServerBootstrapLog`), SSH, agent |
| **Source of Truth** | DB `server_bootstrap_logs` table. Memory is secondary cache. |
| **Critical Rule** | On API startup: all `status='running'` records → `'interrupted'`. |

#### Update Subsystem (`src/modules/updates/`, `update_apply.sh`)

| | |
|---|---|
| **Responsibility** | Check for, download, verify, apply, and roll back code updates. Survive API restart mid-apply. |
| **Inputs** | Manifest from license server, admin trigger |
| **Outputs** | New code on disk, `alembic upgrade head`, `UpdateHistory` DB record, `apply.log` |
| **Dependencies** | License server (manifest), DB (`UpdateHistory`), `update_apply.sh` (separate process) |
| **Source of Truth** | `UpdateHistory` DB record + `apply.log` on disk. Memory progress dict is volatile. |

#### License Subsystem (`src/modules/license/`)

| | |
|---|---|
| **Responsibility** | Validate RSA-signed license, enforce limits (max_clients, max_servers, features), report grace period. |
| **Inputs** | `.env` (activation key), license server (`POST /api/validate` every 4h), startup DB cache |
| **Outputs** | `LicenseState` in-memory dataclass, enforcement decisions in middleware and service layer |
| **Dependencies** | License server (online), `data/license_servers.signed`, `.env` |
| **Source of Truth** | License server is authoritative. DB mirrors last known good state. In-memory `LicenseState` is working copy. |

#### Agent Subsystem (`agent.py`, `agent_bootstrap.py`)

| | |
|---|---|
| **Responsibility** | Thin FastAPI agent on remote VPN servers. Exposes `/health`, WG peer management, command execution. |
| **Inputs** | HTTP API calls from main API, INTERFACE env var |
| **Outputs** | WG/AWG state JSON, command results, health metrics |
| **Dependencies** | Local wg/awg binaries, systemd, psutil |
| **Source of Truth** | Local system state (wg show, psutil). Agent is a projection, not a database. |

#### Billing / Subscriptions (`src/modules/subscription/`)

| | |
|---|---|
| **Responsibility** | Portal subscription lifecycle: activation, renewal (manual + auto), traffic tracking, payment processing. |
| **Inputs** | Payment webhooks (NOWPayments, CryptoPay), admin actions, scheduler triggers |
| **Outputs** | `ClientPortalSubscription` status changes, WG peer enable/disable, notifications |
| **Dependencies** | DB, WGManager, NotificationService |
| **Source of Truth** | DB `client_portal_subscriptions`. Payment provider = external truth for payment status. |

#### Branding (`src/modules/branding.py`)

| | |
|---|---|
| **Responsibility** | Read branding keys from `SystemConfig`. Expose via public `/api/v1/system/branding`. |
| **Inputs** | `SystemConfig` DB rows (`branding_*` keys) |
| **Outputs** | Branding DTO consumed by admin frontend and client portal |
| **Dependencies** | DB |
| **Source of Truth** | DB `system_config` table. |

#### Client Delivery (portal / bot / configs)

| | |
|---|---|
| **Responsibility** | Deliver VPN configs to end users via client portal, Telegram bot, QR codes, file downloads. |
| **Inputs** | Client model, Server model, subscription state |
| **Outputs** | WG/AWG config files, QR codes, Telegram messages |
| **Dependencies** | DB, WGManager/AWGManager |
| **Source of Truth** | DB (client keys, server endpoints, allowed IPs). |

---

## 2. Canonical Status Model

### 2.1 The Problem

The current `server.status` field mixes concerns:

```
ONLINE / OFFLINE / ERROR / INSTALLING / UPDATING / EXPIRED
 └─ lifecycle   └─ health   └─ bootstrap  └─ update
```

A server that is `ONLINE` in lifecycle terms can simultaneously be `DRIFTED`, `UPDATING`, and have `UNHEALTHY` resources. A single enum cannot represent this cleanly.

### 2.2 Four Status Dimensions

| Dimension | Stored In | Updated By | Read By |
|---|---|---|---|
| `lifecycle_status` | `servers.lifecycle_status` in DB | `ServerManager._transition_status()` exclusively | API routes, reconciler, scheduler |
| `health_status` | TTL cache only (60s) | `ServerHealthChecker` | Health API, UI badge |
| `sync_status` | `servers.drift_detected` + `servers.last_reconcile_at` | `StateReconciler` | UI badge, reconciler |
| `operational_status` | `servers.is_active` (bool) | `ServerManager` on enable/disable | WG config generation, client delivery |

### 2.3 Allowed Values Per Dimension

#### `lifecycle_status`

```
CREATING → BOOTSTRAP_PENDING → BOOTSTRAPPING → ONLINE → OFFLINE → DELETING → DELETED
                                                      ↓
                                                   FAILED
                                                   DEGRADED
```

| Value | Meaning |
|---|---|
| `creating` | DB record created, no SSH yet |
| `bootstrap_pending` | Queued for bootstrap, not started |
| `bootstrapping` | Bootstrap task actively running |
| `online` | Agent responsive, WG interface confirmed |
| `offline` | Agent unreachable or WG interface down |
| `degraded` | Partially functional (some peers failing, non-fatal errors) |
| `failed` | Bootstrap failed or unrecoverable error |
| `deleting` | Deletion in progress |
| `deleted` | Soft-deleted |

#### `health_status` (read-only, never persisted)

```
healthy | degraded | unhealthy | unknown
```

#### `sync_status` (persisted as flags, not enum)

```
in_sync | drifted | reconciling | unknown
```

#### `operational_status` (boolean from `is_active`)

```
enabled | disabled
```

### 2.4 Mixing Rules

| Combination | Allowed? | Reasoning |
|---|---|---|
| `lifecycle=online` + `health=unhealthy` | ✅ | Server is up but resources are stressed |
| `lifecycle=online` + `sync=drifted` | ✅ | Server is up but WG peers have drifted |
| `lifecycle=bootstrapping` + `sync=drifted` | ❌ | Reconciler must skip servers in bootstrapping |
| `lifecycle=offline` + `operational=enabled` | ✅ | Server is down but not intentionally disabled |
| `lifecycle=failed` + `operational=enabled` | ✅ | Failed but not yet acted upon |
| `health_status` stored in DB | ❌ | Health is always ephemeral, never persisted |
| `update progress` mixed into `lifecycle_status` | ❌ | Updates have their own `UpdateHistory` record |

---

## 3. State Machines

### 3.1 Server Lifecycle

```
                    ┌──────────────┐
              ┌────►│   creating   │
              │     └──────┬───────┘
              │            │ record created in DB
              │            ▼
              │     ┌──────────────────┐
              │     │ bootstrap_pending │
              │     └──────┬───────────┘
              │            │ bootstrap task started
              │            ▼
              │     ┌──────────────┐   task interrupted / API restart
              │     │ bootstrapping │◄──────────────────────────────┐
              │     └──────┬───────┘                                │
              │      OK    │         FAIL                           │
              │     ┌──────┴──────┐   ┌──────────┐                 │
              │     │   online    │   │  failed  │◄────────────────┘
              │     └──────┬──────┘   └──────────┘
              │            │ SSH fails
              │            ▼
              │     ┌──────────────┐
              │     │   offline    │
              │     └──────┬───────┘
              │            │ partial recovery
              │            ▼
              │     ┌──────────────┐
              │     │   degraded   │
              │     └──────────────┘
              │
              │     ┌──────────────┐
              └─────│   deleting   │──► deleted
                    └──────────────┘
```

**Allowed Transitions:**

| From | To | Trigger | Side Effects |
|---|---|---|---|
| `creating` | `bootstrap_pending` | DB record committed | AuditLog |
| `bootstrap_pending` | `bootstrapping` | Bootstrap task begins | `ServerBootstrapLog` created |
| `bootstrapping` | `online` | S8 health check passes | AuditLog, `ServerBootstrapLog.finish('complete')` |
| `bootstrapping` | `failed` | SSH error / AWG not found / timeout | AuditLog, `ServerBootstrapLog.finish('failed')` |
| `bootstrapping` | `bootstrapping` | API restart | `ServerBootstrapLog` → `interrupted`, new task |
| `online` | `offline` | Health check fails, agent unreachable | AuditLog |
| `online` | `degraded` | Partial failure (some peers broken) | AuditLog |
| `offline` | `online` | Agent responds again | AuditLog |
| `degraded` | `online` | Full recovery confirmed | AuditLog |
| `any` | `deleting` | Admin delete action | WG peers removed, agent uninstalled |
| `deleting` | `deleted` | Cleanup complete | `purge_service()` if proxy, AuditLog |
| `failed` | `bootstrap_pending` | Admin retry | Reset task, new bootstrap |

**Forbidden Transitions:**
- `deleted` → anything (terminal)
- `online` → `creating` (regression)
- `bootstrapping` → `online` without health check confirmation
- Health subsystem → any lifecycle transition

**Terminal States:** `deleted`
**Recoverable:** `failed` → `bootstrap_pending` (via admin retry)
**Retryable:** `bootstrap_pending` (idempotent bootstrap)

---

### 3.2 Proxy Server Lifecycle

Proxy servers use the same `lifecycle_status` enum with key differences:

| Aspect | WG/AWG Server | Proxy Server |
|---|---|---|
| Bootstrap | `agent_bootstrap.py` S1–S8 | `hysteria2.bootstrap()` / `tuic.bootstrap()` |
| Runtime check | `wg show`, agent `/health` | systemd unit status check |
| Reconciler | YES — compares DB peers vs live | **NO** — reconciler skips `is_proxy=True` |
| Delete cleanup | Remove WG peers | `purge_service()` — rm unit + config |
| Service name | `vpnmanager-agent` | `hysteria-{interface}.service` |
| Config path | `/etc/wireguard/{iface}.conf` | `/etc/hysteria/config-{iface}.yaml` |

**Proxy-specific rules:**
- `interface` is immutable after creation
- `service_name` derives deterministically from interface: `hysteria-{interface}`
- Only one proxy instance per `(server_ip, interface)` pair
- `ONLINE` for proxy = systemd unit is `active (running)`, confirmed via SSH

---

### 3.3 Bootstrap Task Lifecycle

```
  (created) ──► running ──► complete     (terminal)
                   │
                   ├──► failed           (terminal, retryable via new task)
                   │
                   └──► interrupted      (terminal, API restart; new task can be created)
```

| State | Stored In | Set By | Meaning |
|---|---|---|---|
| `running` | DB + memory | `create_task()` | Task is actively executing |
| `complete` | DB | `BootstrapTask.finish('complete')` | All stages passed |
| `failed` | DB | `BootstrapTask.finish('failed', error)` | Unrecoverable error during stages |
| `interrupted` | DB | `mark_interrupted_tasks()` on startup | API restarted during execution |

**Allowed Transitions:**
- `running` → `complete` | `failed` | `interrupted`
- `interrupted` / `failed` → new separate task (NOT a transition on same record)

**Forbidden:**
- `complete` → any (terminal)
- Updating `task_id` on existing record (immutable)

**Side Effects:**
- `complete` → `server.lifecycle_status` → `online` via `_transition_status()`
- `failed` → `server.lifecycle_status` → `failed` via `_transition_status()`
- `interrupted` → no automatic lifecycle change; UI shows "interrupted"; admin must retry

---

### 3.4 Update Lifecycle

```
available ──► downloading ──► downloaded ──► verified ──► ready_to_apply
                                                               │
                                                          admin trigger
                                                               │
                                                           applying
                                                               │
                                                    ┌──────────┴──────────┐
                                               applied              failed / rolled_back
                                           (terminal ✅)           (terminal)
```

| State | Stored In | Set By |
|---|---|---|
| `available` | `UpdateHistory.status` | `checker.py` after manifest verify |
| `downloading` | Memory + DB | `manager.py` download start |
| `downloaded` | DB | SHA-256 verified, file on disk |
| `verified` | DB | RSA signature confirmed |
| `ready_to_apply` | DB | Pre-apply checks passed (disk space, flock) |
| `applying` | DB + `apply.log` on disk | `update_apply.sh` running |
| `applied` | DB | S9 health check passed, VERSION updated |
| `failed` | DB | Any stage failure |
| `rolled_back` | DB | `ROLLBACK=1` completed successfully |

**Key Property — Apply Survivability:**
`update_apply.sh` runs as a separate process with its own `apply.log`. If API restarts mid-apply, `update_apply.sh` continues. On next API start, progress endpoint falls back to reading `apply.log` from `backup_path` on disk.

**Forbidden:**
- `applied` → `applying` (must go through `available` again via new version)
- `rolled_back` → `applied` (rollback is terminal for that version attempt)

---

### 3.5 License Lifecycle

```
  (activation) ──► active ──────────────────────────────────────► expired
                      │                                               │
                      │  server unreachable                           │ grace period
                      ▼                                               ▼
               unreachable_but_cached ──► active (reconnects)     blocked
                      │                                               │
                      │ > 72h                                         │ valid key provided
                      ▼                                               ▼
                   blocked                                         active
```

| State | Meaning | Enforcement |
|---|---|---|
| `active` | Validated within last 4h | Full access |
| `grace` | Expiry within 7 days | Full access + warning banner |
| `expired` | `expires_at` passed, server confirmed | License routes only |
| `blocked` | >72h without server OR validation rejected | Only `/updates`, `/system/restart`, `/system/license` |
| `unreachable_but_cached` | Server 404/timeout, within 72h grace | Full access, warning in UI |
| `invalid` | RSA signature failed, tampered payload | Immediate block, no grace |

**`LicenseState` authority:**
- All reads: `get_license_state()` → atomic snapshot via `dataclasses.replace()`
- All writes: `_apply_payload()` or targeted field update under `_state_lock`
- Persisted to: `.env` (activation key), DB `SystemConfig` (last known tier/limits)
- In-memory `LicenseState` rebuilt from DB on API restart — no cold-start block

---

### 3.6 Agent Connection Lifecycle

```
unknown ──► provisioning ──► online ──► offline ──► online   (recoverable loop)
                │                         │
                │ bootstrap failed         │ > N consecutive failures
                ▼                         ▼
              error                     stale
```

| State | Meaning | Set By |
|---|---|---|
| `unknown` | Agent never contacted, server just created | Initial |
| `provisioning` | Bootstrap running, agent not yet installed | `bootstrapping` lifecycle state |
| `online` | `/health` responded within last check cycle | Health checker |
| `offline` | Last check failed, recent history of success | Health checker |
| `stale` | No successful contact > configurable threshold | Health checker |
| `error` | Bootstrap failed, agent in broken state | Bootstrap task |

> This is a projection of `health_status` + `lifecycle_status`. Never stored as an independent field. UI derives it from `lifecycle_status` + last health check timestamp.

---

## 4. Source of Truth Matrix

| Entity | Source of Truth | Volatile Cache / Projections | Updated By | In Case of Conflict |
|---|---|---|---|---|
| Server lifecycle | `servers.lifecycle_status` in DB | UI render | `ServerManager._transition_status()` only | DB wins |
| Server health | TTL memory cache (60s) | Never persisted | `ServerHealthChecker` | Live system wins |
| Proxy runtime state | systemd unit status (live) | DB `server.status` | `hysteria2/tuic.bootstrap()`, systemd | Live systemd wins |
| WG peer live state | `wg show` / `awg show` output | DB `clients.allowed_ips`, `wg_public_key` | WG kernel | WG kernel wins; DB is intended state |
| Subscription state | `client_portal_subscriptions.status` in DB | Memory (scheduler reads DB each cycle) | `SubscriptionManager`, scheduler | DB wins |
| License state | License server (online) | `LicenseState` in-memory, DB `SystemConfig` | `online_validator._apply_payload()` | License server wins; DB cache when unreachable |
| Bootstrap task state | `server_bootstrap_logs` in DB | Memory `BootstrapTask` object | `bootstrap_logger.py` | DB wins (memory is write-through) |
| Update state | `update_history` in DB + `apply.log` on disk | Memory progress dict | `update_apply.sh`, `manager.py` | `apply.log` wins over memory after restart; DB is final record |
| Agent connection | Live `/health` endpoint | `servers.last_seen_at`, health cache | `ServerHealthChecker` | Live agent wins |
| WG drift state | `servers.drift_detected` in DB | In-memory reconciler state | `StateReconciler` | DB + live wg show combined; reconciler resolves |

---

## 5. Current Architectural Risks

### R1 — Scheduler inside API process
| | |
|---|---|
| **Severity** | Medium |
| **Risk** | `monitoring_cycle()` and `backup_cycle()` run as asyncio tasks inside the API process. A slow monitoring cycle (SSH timeouts, large DB query) blocks the event loop. An API crash kills all background work without any record. |
| **Minimal Fix** | Add per-cycle timeout: `asyncio.wait_for(asyncio.to_thread(...), timeout=MONITOR_INTERVAL * 0.9)`. Already extracted to `scheduler.py` — next step is timeout guard. |
| **Deferrable** | Yes. Acceptable for single-server deployments. |

### R2 — Bootstrap interrupted state has no auto-recovery
| | |
|---|---|
| **Severity** | Medium |
| **Risk** | `mark_interrupted_tasks()` marks stale tasks as `interrupted` but does NOT automatically re-trigger bootstrap. Server stays in `bootstrapping` lifecycle_status forever until admin manually retries. |
| **Minimal Fix** | On `mark_interrupted_tasks()`, if `server.lifecycle_status == bootstrapping`, transition it to `failed`. Surfaces the problem clearly in UI. Admin then retries. |
| **Deferrable** | **No.** Silent stuck `bootstrapping` state is confusing and prevents server being usable. |

### R3 — Update progress after restart is best-effort
| | |
|---|---|
| **Severity** | Low |
| **Risk** | Progress fallback reads `apply.log` from disk, but path comes from `UpdateHistory.backup_path` which may point to a cleaned-up directory. |
| **Minimal Fix** | Add `updated_at` to `UpdateHistory`. If `applying` and `updated_at > 30 min` with no progress — transition to `failed` automatically. |
| **Deferrable** | Yes. Current fallback is good enough for typical restarts. |

### R4 — Memory state vs DB state split in license
| | |
|---|---|
| **Severity** | Medium |
| **Risk** | `LicenseState` is rebuilt only on first validator check (within 4h of startup). Between startup and first check, state comes from DB cache. If license was revoked while offline >72h, the first 0–4h window accepts requests incorrectly. |
| **Minimal Fix** | On API startup, trigger one immediate license validation check synchronously before serving requests, with a 5s timeout. |
| **Deferrable** | Yes. Edge case. Grace period policy already covers this window. |

### R5 — Status mutation from multiple places
| | |
|---|---|
| **Severity** | **High** |
| **Risk** | Despite `_transition_status()` being introduced, there may be paths in `state_reconciler.py`, `monitoring_cycle()`, or route handlers that still directly set `server.status`. Any direct mutation bypasses audit log. |
| **Minimal Fix** | `grep -rn ".status = ServerStatus" src/` — any hit outside `server_manager.py` is a violation. Make `server.status` a Python property that raises `AttributeError` on direct assignment. |
| **Deferrable** | **No.** This is the #1 source of silent status bugs. |

### R6 — Reconciler has no exclusion guard for non-WG servers
| | |
|---|---|
| **Severity** | Medium |
| **Risk** | Reconciler iterates over all servers. If `is_proxy` flag is not checked consistently, it will attempt `wg show` on a proxy server's interface → false drift detections. |
| **Minimal Fix** | Top of reconciler main loop: `if server.is_proxy: continue`. Verify this guard exists and is tested. |
| **Deferrable** | **No.** Should be confirmed immediately. |

### R7 — Long-running SSH tasks during API restart
| | |
|---|---|
| **Severity** | Low |
| **Risk** | SSH operations (bootstrap, WG peer add) are blocking calls in threads. During graceful shutdown, these threads are abandoned mid-execution, leaving remote server in partial state. |
| **Minimal Fix** | On `SIGTERM`, log active bootstrap task IDs. `mark_interrupted_tasks()` already handles DB cleanup. No code change needed now. |
| **Deferrable** | Yes. `mark_interrupted_tasks()` provides acceptable recovery. |

### R8 — Proxy systemd service discovery on DB restore
| | |
|---|---|
| **Severity** | Medium |
| **Risk** | If a proxy server DB record is restored from backup and `bootstrap()` is called again, an old config file with different parameters may not be replaced if `bootstrap()` has conditional file writes. |
| **Minimal Fix** | Ensure `bootstrap()` always writes config file unconditionally. Already done for unit file — verify config file has same policy. |
| **Deferrable** | Yes. Edge case only on DB restore scenarios. |

### R9 — Audit log completeness
| | |
|---|---|
| **Severity** | Medium |
| **Risk** | `AuditLog` covers server status transitions and some admin actions. Payment events, subscription state changes, and license events are NOT consistently in audit log. |
| **Minimal Fix** | Add `AuditLog` entries in: `complete_payment()`, `check_and_expire_subscriptions()`, license `blocked` transition. |
| **Deferrable** | Yes. Should be done before commercial release. |

### R10 — No pg_advisory_lock on reconciler
| | |
|---|---|
| **Severity** | Low |
| **Risk** | If two API instances run simultaneously (rolling update or misconfiguration), both run reconciler at the same time → duplicate `wg set` commands. |
| **Minimal Fix** | Wrap reconciler main loop in `SELECT pg_try_advisory_lock(hashtext('reconciler'))`. |
| **Deferrable** | Yes. Single-process deployment makes this theoretical. |

---

## 6. Minimal Target Architecture

### 6.1 Leave As-Is
- Route handlers (`src/api/routes/`) — thin, delegate well
- WG/AWG managers — stable, well-tested (250+ unit tests)
- Health subsystem — clean TTL cache pattern
- Branding module — simple, correct
- NotificationService — adequate
- Client delivery (portal, bot, config generation)

### 6.2 Logical Separation Needed

| Current Situation | Target Boundary |
|---|---|
| `server_manager.py` does orchestration + DB mutations + SSH | Extract: `ServerOrchestrator` (lifecycle) vs `ServerRepository` (DB reads/writes) |
| `monitoring_cycle()` does 6 unrelated things | Split into named functions: `_cycle_traffic_sync()`, `_cycle_autorenewal()`, `_cycle_expiry()`, `_cycle_notifications()`, `_cycle_payments()` — still one cycle, but readable |
| Reconciler and health checker both SSH to servers | Shared `ServerConnectivityCache` — avoid duplicate SSH per cycle |

### 6.3 Where to Introduce Service Layer

| Operation | Current | Target |
|---|---|---|
| Server create | Route → `ServerManager` directly | Route → `ServerService.create()` → ServerManager |
| Bootstrap retry | No dedicated path | `ServerService.retry_bootstrap()` — validates preconditions, creates new task |
| License enforcement | Inline in middleware | `LicenseService.check_limit(resource, count)` — single enforcement point |
| Update apply | Route → manager directly | `UpdateService.apply()` — pre-checks, lock, delegate |

### 6.4 Where to Introduce Command Handlers

Not needed now. The project is not complex enough to justify CQRS. The `_transition_status()` pattern is a sufficient command handler for the most critical operation.

### 6.5 Where Persisted Task Model Is Required

| Task Type | Current State | Action Required |
|---|---|---|
| Bootstrap | DB (`ServerBootstrapLog`) ✅ | None |
| Update apply | DB (`UpdateHistory`) + `apply.log` ✅ | None |
| Bulk client disable | In-memory, no record | Add if bulk operations > 100 clients |
| Backup | No task record | Add `BackupHistory` with status |

### 6.6 Where Idempotency Is Required

| Operation | Idempotent? | Risk If Not |
|---|---|---|
| `bootstrap()` | ✅ | Low |
| `complete_payment()` | ✅ (SELECT FOR UPDATE + status check) | Medium |
| `add_peer()` to WG | ⚠️ Partial | Medium — duplicate peer in WG |
| `purge_service()` | ✅ (`2>/dev/null` on all commands) | Low |
| License activation | ✅ (server-side idempotent) | Low |
| Subscription auto-renewal | ✅ (last_renewal 24h guard) | Low |

### 6.7 Where Status Projection / Read Model Is Needed

The UI currently reads raw `server.status` and `drift_detected` and combines them in Vue components. A `ServerStatusProjection` DTO should combine:

```
lifecycle_status + drift_detected + last_health_check + operational_status
→ { display_status, display_color, actions_available }
```

This DTO is computed on read, **never stored**.

### 6.8 Where Audit Log Is Mandatory

| Operation | Audit Log? |
|---|---|
| Server status transition | ✅ (`_transition_status()`) |
| Client enable/disable | ✅ (existing `AuditLog`) |
| Payment complete | ❌ Add |
| Subscription expire/block | ❌ Add |
| License blocked | ❌ Add |
| Admin login | ✅ |
| Bootstrap complete/failed | ⚠️ Partial — in `ServerBootstrapLog`, not `AuditLog` |
| Update applied | ✅ (`UpdateHistory`) |
| Config downloaded | ✅ |

### 6.9 Where Memory-Only State Is Forbidden

| Data | Current | Rule |
|---|---|---|
| Bootstrap task progress | DB-persisted ✅ | Compliant |
| Update progress | Memory + `apply.log` | `apply.log` is sufficient; DB record must be terminal |
| License state | Memory only at runtime | Must persist last-known-good to DB for cold-start |
| Health check results | Memory (TTL cache) | Correct — health is ephemeral by design |
| Active update flock | In-memory flag | Correct — flock is process-level guard |

---

## 7. Architectural Rules

**R01 — Every long-running operation must have a persisted task record.**
Before any operation that takes >2 seconds or involves SSH, a DB record must exist with `status='running'`. If the process restarts, the record survives.

**R02 — Every lifecycle status transition must go through `_transition_status()`.**
Direct assignment `entity.status = X` is forbidden. The transition method writes AuditLog, logs the change, and is the single enforcement point.

**R03 — UI never invents status.**
The frontend never derives lifecycle status from heuristics. The API must provide a computed `display_status` field. Frontend renders what it receives.

**R04 — Health checks never trigger lifecycle transitions.**
The health subsystem is read-only. A failed health check produces `health_status=unhealthy`. It does not set `lifecycle_status=offline`. Only explicit operations change lifecycle.

**R05 — Reconciler never acts on proxy servers.**
`is_proxy=True` servers are excluded from all WG reconciler logic. Proxy runtime is managed by systemd, not by WG peer tracking.

**R06 — Each proxy server instance owns exactly one systemd unit and one config file.**
Names derive deterministically from interface: `hysteria-{interface}.service` / `/etc/hysteria/config-{interface}.yaml`. Two proxy servers can never share a unit or config.

**R07 — External side effects must be idempotent.**
SSH commands, WG peer add/remove, systemd unit writes: all must be safe to repeat. Use `2>/dev/null`, pre-checks, and `wg set` (upsert) over `wg addconf` (append).

**R08 — Scheduler is never a source of truth.**
The monitoring cycle reads DB state and writes back DB state. It never holds authoritative state in memory between cycles. Each cycle starts fresh from DB.

**R09 — License state must survive API cold start without blocking.**
On startup, the last known license state must be loadable from DB (`SystemConfig` cache) without requiring a network call. The online validator catches up asynchronously within 4h.

**R10 — Destructive operations must be auditable and reversible where possible.**
Delete operations: log to AuditLog before executing. Where reversal is possible (client disable vs delete), prefer soft operations. `purge_service()` is the point of no return for proxy deletion and must be logged.

**R11 — The update mechanism must be able to operate when the license is expired.**
`/api/v1/updates` and `/api/v1/system/restart` always bypass license middleware. A broken license must be fixable via update without manual server access.

**R12 — Memory state that affects user-visible behavior must have a DB fallback.**
`LicenseState`: DB cache for cold start. `UpdateHistory`: `apply.log` for restart recovery. `BootstrapTask`: full DB persistence. No user-affecting state lives only in memory.

**R13 — Bootstrap interrupted ≠ bootstrap failed.**
`interrupted` = process cut short by external event (API restart). `failed` = operation was attempted and produced an error. `interrupted` can be safely retried immediately; `failed` should be investigated first.

**R14 — Status projections are computed, never stored.**
The combined display status shown in UI (lifecycle + health + drift + operational) is always a runtime computation. Never persist a derived status that can become stale.

**R15 — Audit completeness covers: lifecycle, payments, license enforcement, destructive operations.**
If an action changes money, access, or existence of a resource — it must have an `AuditLog` entry. "It's in the logs" is not acceptable; it must be in the structured `AuditLog` table.

---

## 8. Definition of Done — Stage 0

Stage 0 is complete when **all** of the following criteria are met.

### Code Criteria

| # | Criterion | How to Verify |
|---|---|---|
| C1 | Zero direct `server.status = ServerStatus.X` outside `_transition_status()` | `grep -rn ".status = ServerStatus" src/` → 0 results outside `server_manager.py` |
| C2 | `StateReconciler` skips proxy servers | Read reconciler loop — `is_proxy` guard present; unit test confirms skip |
| C3 | Bootstrap `interrupted` → server transitions to `failed` lifecycle_status | `mark_interrupted_tasks()` calls `_transition_status(server, FAILED)` for `bootstrapping` servers |
| C4 | `bootstrap()` always writes unit file and config unconditionally | Read `hysteria2.bootstrap()` — no conditional skip on config write |
| C5 | `purge_service()` called on proxy server delete, not `stop_service()` | Read `delete_server()` in `server_manager.py` |
| C6 | License last-known-good persisted to DB on each successful validation | `_apply_payload()` writes to `SystemConfig` |
| C7 | Immediate license check on API startup (5s timeout, non-blocking) | Read `main.py` lifespan |
| C8 | `AuditLog` entries in `complete_payment()`, `check_and_expire_subscriptions()`, license `blocked` | Grep for `AuditLog` in those functions |

### Behavioral Criteria

| # | Criterion | How to Verify |
|---|---|---|
| B1 | Bootstrap task survives API restart — status readable after restart | Manual: kill API mid-bootstrap, restart, check `/servers/{id}/bootstrap/{task_id}` |
| B2 | Update progress readable after API restart | Manual: kill API mid-update, restart, poll `/updates/progress/{id}` — returns log lines |
| B3 | Proxy server delete removes systemd unit and config file | Manual: create proxy, delete, confirm `hysteria-proxy-hys0.service` does not exist |
| B4 | Two proxy servers on same host have different unit files and configs | Manual: create two Hysteria2 proxies, inspect `/etc/systemd/system/` |
| B5 | Expired license does not block `/api/v1/updates` | Integration: `LICENSE_CHECK_ENABLED=true`, expired license, `GET /updates/status` → 200 |

### Documentation Criteria

| # | Criterion |
|---|---|
| D1 | This specification is committed to `docs/architecture.md` in the repo |
| D2 | `arch_review.md` in memory is consistent with implemented state |
| D3 | MEMORY.md reflects current version (v1.2.78) and migration state (017 in dev, 016 on prod) |

### Test Criteria

| # | Criterion |
|---|---|
| T1 | All existing unit tests pass (250/250) |
| T2 | Bootstrap E2E passes on VM (9/9) |
| T3 | Security suite passes (60/60) |
| T4 | New unit tests for `mark_interrupted_tasks()` → server lifecycle transition |
| T5 | New unit test for reconciler proxy exclusion |

---

**When all C1–C8, B1–B5, D1–D3, T1–T5 are met → Stage 0 complete → proceed to Stage 1 (Updates hardening).**

---

## 9. Product Operations Addendum

### 9.1 Runtime Layout

Current product runtime layout:

```text
/opt/vpnmanager/
  current -> releases/<version>
  releases/
  staging/
  backups/
  update-lock/
```

Legacy installs may still run under `/opt/spongebot` in compatibility mode.

### 9.2 Operational Modes

Resolved operational modes, in priority order:
- `rollback_in_progress`
- `update_in_progress`
- `maintenance`
- `license_expired_readonly`
- `license_grace`
- `degraded`
- `normal`

Explicit mode source:
- maintenance flag in DB/system config

Derived mode sources:
- update/rollback from update subsystem
- license modes from license subsystem
- degraded from system health evaluation

### 9.3 Product Lifecycle

Operational lifecycle for the sold product:

```text
install -> operate -> update -> backup -> restore -> rollback -> support
```

Roles:
- CLI: canonical operational interface on the server
- API: application/runtime interface for UI and integrations
- UI: operator-facing control surface for day-to-day work

### 9.4 Restore Scope

Current restore scope is intentionally narrower than a full filesystem replay.

Guaranteed restore today:
- DB
- `.env`
- local WireGuard / AmneziaWG configs
- product service restart
- post-restore health evaluation

Not guaranteed by current restore backend:
- SSL certificates
- nginx config recreation from backup
- full `releases/current` tree replay
- remote agent deployment state
- external DNS / public IP migration side effects
