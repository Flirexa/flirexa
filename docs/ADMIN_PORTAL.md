# ADMIN_PORTAL — Administrator Web Panel  @ADMIN_PORTAL

> Read after: `CHILD_NODES.md`
> Next: `CLIENT_PORTAL.md`

---

## OVERVIEW

| Item | Value |
|------|-------|
| URL | `http://<server-ip>:10086` |
| Technology | Vue.js 3 + Vite + Pinia + Bootstrap 5 |
| Themes | Light / Dark — toggle via sun/moon button in top bar |
| Languages | 5 (English, Russian, German, French, Spanish) |
| Build output | `src/web/static/dist/` |
| Source | `src/web/frontend/src/` |
| Served by | FastAPI static mount + SPA catch-all |

---

## USER MANAGEMENT  @ADMIN_USERS

### Client Management (VPN clients)

**View:** `src/web/frontend/src/views/Clients.vue`
**API:** `GET/POST/PUT/DELETE /api/v1/clients`

| Feature | Details |
|---------|---------|
| List clients | Table with search, filter by server, filter by status |
| Create client | Name, server selection — keys auto-generated |
| Enable/Disable | Toggle peer on WireGuard interface |
| Traffic display | `traffic_used_rx + traffic_used_tx` from DB (updated every 60s) |
| Traffic limit | Set MB limit → auto-disable when exceeded |
| Bandwidth limit | Set Mbps → TC HTB on child node |
| Expiry date | Set datetime → auto-disable when passed |
| Config download | WireGuard `.conf` file |
| QR code | PNG via `GET /clients/{id}/qrcode` |
| Delete | Removes peer from WireGuard, deletes from DB |

**Note:** `traffic_limit_mb` is the DB field (NOT `traffic_limit`). Frontend must use `traffic_limit_mb`.

### Telegram Bots

**View:** `src/web/frontend/src/views/Bots.vue`
**API:** `/api/v1/bots/*`

- Start/stop/restart admin bot and client bot
- View logs from systemd
- Update bot tokens and allowed users via UI form
- Tokens masked in display (`7565...Q`)

---

## TARIFF / PLAN MANAGEMENT  @ADMIN_TARIFFS

**View:** `src/web/frontend/src/views/Subscriptions.vue`
**API:** `GET/POST/DELETE /api/v1/payments/plans`

Plans sync automatically to:
- Client Portal (via `GET /client-portal/subscription/plans`)
- Android app (via same API, fetched in SubscriptionsFragment)

### Plan Fields

| Field | Type | Description |
|-------|------|-------------|
| tier | string | Unique identifier (e.g. `basic`, `pro`, `enterprise`) |
| name | string | Display name |
| description | text | Optional description |
| max_devices | int | Max simultaneous WireGuard configs |
| traffic_limit_gb | float | Monthly traffic limit (null = unlimited) |
| bandwidth_limit_mbps | int | Speed cap (null = unlimited) |
| price_monthly_usd | float | Monthly price |
| price_quarterly_usd | float | Quarterly price (optional) |
| price_yearly_usd | float | Yearly price (optional) |
| active | bool | Visible to clients |

---

## SERVER MANAGEMENT  @ADMIN_SERVERS

**View:** `src/web/frontend/src/views/Servers.vue`
**API:** `/api/v1/servers/*`

| Feature | Details |
|---------|---------|
| List servers | Cards with status badge (Local / SSH / 🤖 Agent) |
| Add server | Manual (keys) or Auto-discover via SSH |
| Start/Stop/Restart | Controls WireGuard interface via agent/SSH |
| Stats | Peer count, rx/tx, uptime (cached 30s) |
| Agent modal | Status, test connection, reinstall, delete agent |
| Discover | SSH credentials → auto-import server + all clients |

### Server Badges
- No badge: local server (203.0.113.1)
- **SSH** (orange): remote, SSH mode
- **🤖 Agent** (green): remote, HTTP agent mode

---

## LOGS & ANALYTICS  @ADMIN_LOGS

**View:** `src/web/frontend/src/views/Logs.vue`
**API:** `GET /api/v1/system/logs`

- Full audit log table (paginated)
- Filter by: action type, target type, date range
- Actions: CLIENT_CREATE, CLIENT_ENABLE, CLIENT_DISABLE, SERVER_CREATE, PAYMENT_CONFIRMED, etc.
- Details stored as JSON (`details` column)

**Dashboard stats:**
- Total clients, active clients, online servers
- Total traffic (rx + tx from DB)
- System health: CPU%, Memory%, Disk%
- Expiry summary: expiring in 7/30 days
- Traffic summary: clients near/over limits

---

## SETTINGS  @ADMIN_SETTINGS

**View:** `src/web/frontend/src/views/Settings.vue`
**CRITICAL:** This file uses **Options API + Bootstrap cards** — NOT Composition API.
Composition API causes silent crash on this component.

| Setting | Where stored |
|---------|-------------|
| Bot tokens | `.env` file + `SystemConfig` DB table |
| CryptoPay token | `.env` (CRYPTOPAY_API_TOKEN) + Settings UI |
| PayPal / NOWPayments | `.env` + hot-reload via Settings UI |
| SMTP Email | `.env` + hot-reload via Settings UI |
| Telegram Notifications | `system_config` DB (6 keys `notify_*`) |
| **Backup Config** | `system_config` DB (13 keys `backup_*`) |
| API server URL | Admin-only config display |
| System health | Live check (DB + WG connection) |

### Backup Control Center

Расположен в Settings.vue, включает:
- **3 stat cards:** статус (enabled/disabled), следующий бекап, количество бекапов
- **Schedule:** частота (6ч/12ч/24ч/48ч/неделя), час UTC, auto-backup вкл/выкл, auto-cleanup + retention
- **Storage:** Local path / Network mount (SMB/NFS)
- **Network mount:** тип, адрес, логин/пароль (маскируется), mount point, опции, Mount/Unmount/Test Write
- **History:** список бекапов с размером, серверами, клиентами, кнопки Restore DB и Delete

**Backend endpoints:**
- `GET/POST /system/backup-settings` — конфиг из SystemConfig
- `POST /system/backup-mount` / `backup-unmount` — монтирование NFS/SMB
- `GET /system/backup-mount-status` — статус монтирования
- `POST /system/backup-test-write` — тест записи
- `DELETE /backup/{id}` — удаление бекапа

**Security:** path validation (blacklist опасных путей, блок `..`), mount options regex whitelist, числовые параметры range-checked, пароль маскируется при отдаче.

---

## FRONTEND ARCHITECTURE

### Stores (Pinia)

| Store | File | Manages |
|-------|------|---------|
| clients | `stores/clients.js` | fetchClients, createClient, toggleClient, updateLimits |
| servers | `stores/servers.js` | fetchServers, createServer, serverAction, discoverServer |
| system | `stores/system.js` | fetchStatus, toggleDarkMode, setTheme, sidebarOpen |

### API Client (`src/web/frontend/src/api/index.js`)

Axios instance with:
- Base URL: `/api/v1/`
- Request interceptor: inject JWT token (if AUTH_ENABLED)
- Response interceptor: handle 401 (logout)
- Modules: `clientsApi`, `serversApi`, `paymentsApi`, `botsApi`, `systemApi`, `backupApi`, `tariffsApi`, `trafficApi`, `portalUsersApi`, `promoCodesApi`, `appAccountsApi`

### i18n

- `vue-i18n` v9, Composition API mode (`legacy: false`)
- Auto-detect: `localStorage('sb_lang')` → browser language → `en` fallback
- Files: `src/i18n/locales/{en,ru,de,fr,es}.js`
- Usage: `$t('key')` in templates, `t('key')` in setup()

### Themes

Light/dark toggle via a single sun/moon button (☀️/🌙) in the top navigation bar. Click once to switch. State persisted in `localStorage` (`sb_theme`). CSS custom properties with `[data-theme="dark"]` selector on `<html>`. Mobile-safe: uses `touch-action: manipulation` guard to prevent double-fire on iOS/Android.

### HelpTooltip System

Context-sensitive `?` icons appear next to labels and headings throughout the admin panel. Hover (desktop) or tap (mobile) to show a bubble with a short explanation. Tooltips use `<Teleport to="body">` so they are never clipped by overflow containers. Translations are in the `help:` section of each locale file (`src/i18n/locales/{en,ru,de,fr,es}.js`). The component is globally registered: `app.component('HelpTooltip', HelpTooltip)` in `main.js`.

---

## BUILD & DEPLOY

```bash
# Build admin frontend
cd src/web/frontend
npm run build  # → src/web/static/dist/

# Build client portal
cd src/web/client-portal
npm run build  # → src/web/client-portal-dist/
```

Vite is configured with `manualChunks` for optimal caching:
- `vendor-vue` — Vue, Vue Router, Pinia, vue-i18n (~169 KB)
- `vendor-bootstrap` — Bootstrap JS
- `vendor-charts` — ApexCharts (~528 KB, cached separately)

Deploy via `deploy.sh` (rsync source + dist → `/opt/vpnmanager/`, run migrations, restart services) or via the admin panel update mechanism.

---

*Tags: @ADMIN_PORTAL @ADMIN_USERS @ADMIN_TARIFFS @ADMIN_SERVERS @ADMIN_LOGS @ADMIN_SETTINGS*
