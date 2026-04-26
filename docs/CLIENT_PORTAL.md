# CLIENT_PORTAL — Client Self-Service Dashboard  @CLIENT_PORTAL

> Read after: `ADMIN_PORTAL.md`
> Next: `ANDROID_APP.md`

---

## OVERVIEW

| Item | Value |
|------|-------|
| URL | `http://<server-ip>:10090` |
| Service | `vpnmanager-client-portal.service` |
| Entry point | `client_portal_main.py` (FastAPI, port 10090) |
| Frontend source | `src/web/client-portal/src/` |
| Frontend build | `src/web/client-portal-dist/` (copied to static) |
| API routes | `src/api/routes/client_portal.py` |
| Router prefix | `/client-portal/` (all API routes) |

---

## AUTHENTICATION  @CLIENT_AUTH

### JWT-based (email + password)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/client-portal/auth/register` | POST | Register new account |
| `/client-portal/auth/login` | POST | Login → returns `access_token` |
| `/client-portal/auth/me` | GET | Get current user info |
| `/client-portal/auth/verify-email` | POST | Email verification (optional) |

**Token storage:** Android app → `TokenManager` (SharedPreferences). Client portal → localStorage.
**Token format:** `Authorization: Bearer <jwt>`

### User model (`client_users` table)
```
id, email (unique), password_hash, username, full_name,
email_verified, telegram_id, created_at
```

---

## SUBSCRIPTIONS  @CLIENT_SUBS

### Subscription flow:
```
Client → view plans (GET /subscription/plans)
       → select plan → create invoice (POST /payments/create-invoice)
       → redirect to CryptoPay payment URL
       → CryptoPay webhook → server creates WireGuard config
       → client can download config / use Android app
```

### Plan sync:
Plans created in Admin Portal → auto-appear in Client Portal and Android app.
No cache — fetched on every view load.

### Subscription endpoints:
| Endpoint | Description |
|----------|-------------|
| `GET /subscription` | User's current subscription (tier, status, expiry, traffic) |
| `GET /subscription/plans` | All active plans (synced from Admin) |
| `POST /payments/create-invoice` | Create CryptoPay invoice → returns `payment_url` |

---

## DEVICES (WireGuard Configs)  @CLIENT_DEVICES

### Automatic config (primary flow):
```
Login → POST /wireguard/auto-setup
→ find client inactive >24h OR create new one
→ return {client_id, config (WG .conf text), name}
→ Android imports config automatically
```

### Manual device management:
| Endpoint | Description |
|----------|-------------|
| `GET /wireguard/clients` | List user's WireGuard configs |
| `GET /wireguard/config/{id}` | Download specific config as text |
| `DELETE /wireguard/clients/{id}` | Delete a config |

### One-account, one-device model:
- New accounts get one free config auto-assigned on first login
- Additional configs require active subscription
- Android app always uses auto-setup on login — user never manually selects config

---

## APK DOWNLOAD  @CLIENT_APK

**URL:** `http://203.0.113.1:10090/download/app`
**Mechanism:** Handled inside catch-all in `client_portal_main.py`:

```python
@app.get("/{full_path:path}")
async def serve_frontend(request, full_path):
    if full_path == "download/app":
        # Serves latest versioned APK (SpongeBot-v*.apk), fallback to spongebot-vpn.apk
        versioned = sorted(glob("SpongeBot-v*.apk"), reverse=True)
        return FileResponse(versioned[0], ...)
    if full_path == "download/app/version":
        return JSONResponse(json.loads("apk-version.json"))  # version metadata
    # ... SPA fallback
```

**CRITICAL:** The catch-all is `@app.get()` only — API routes (POST etc.) are NOT intercepted.

### APK in Client Portal UI:
- Dashboard: download card with green gradient button
- Login: secondary download button below main form
- i18n keys: `dash.downloadApp`, `dash.downloadAppDesc`, `dash.downloadAPK` (5 languages)

---

## APP VERSION / UPDATES  @CLIENT_VERSION

| Endpoint | Description |
|----------|-------------|
| `GET /client-portal/version` | Returns current app version info |

Response:
```json
{
  "version": "1.0.1",
  "version_code": 101,
  "download_url": "/download/app",
  "release_notes": "SpongeBot VPN — ocean-themed WireGuard client"
}
```

**Update trigger:** Bump `version_code` here AND in `gradle.properties`. Android checks on launch.

---

## FRONTEND STRUCTURE

```
src/web/client-portal/src/
├── main.js              # Vue app entry, i18n, router; registers HelpTooltip globally
├── utils.js             # Shared: formatDate, formatDateTime, formatBytes
├── router/index.js      # Routes: /login, /dashboard, /subscription, /payments, /corporate
├── api/                 # Axios client, base URL = /client-portal/
├── stores/auth.js       # Pinia: login, logout, token, user info
├── components/
│   ├── HelpTooltip.vue  # Context ? tooltip (Teleport, hover+tap, dark-theme aware)
│   └── Layout.vue       # App shell with light/dark toggle (☀️/🌙)
├── views/
│   ├── Login.vue        # Email/password form + APK download button
│   ├── Dashboard.vue    # Subscription status + APK download card + recent payments
│   ├── Plans.vue        # Plan list + purchase flow
│   ├── Payments.vue     # Payment history
│   ├── Support.vue      # Support tickets
│   └── CorporateVPN.vue # Corporate network management (sites, keys, diagnostics)
└── i18n/locales/
    └── {en,ru,de,fr,es}.js  # 5 languages; help: section for HelpTooltip text
```

### HelpTooltip

`?` icons next to section headings and important labels. Uses `<Teleport to="body">` to avoid overflow clipping. Tap on mobile, hover on desktop. Globally registered in `main.js`.

### Build
```bash
cd /opt/vpnmanager/src/web/client-portal
npm run build  # → outputs to src/web/client-portal-dist/
```

Then deploy: `cp -r client-portal-dist/ /opt/spongebot/src/web/`
Served via static mount: `STATIC_DIR/assets` → `/assets`, catch-all → `index.html`

---

## INTEGRATION WITH ADMIN PANEL

| What | How |
|------|-----|
| Plans | Client portal calls Admin API via `AdminAPIClient` (internal HTTP) |
| WireGuard configs | Client portal calls Admin API: `GET /api/v1/clients/{id}/config` |
| Auto-setup | Client portal creates client via Admin API if none exists |
| Authentication | Separate `client_users` table — NOT admin users |

**`AdminAPIClient`** (`src/modules/subscription/admin_api_client.py`):
- Base URL: `http://localhost:10086`
- Auth: `X-Service-Token: <SERVICE_API_TOKEN>` header
- Used for: creating WG clients, getting configs, checking client status

---

## NO-CACHE HEADERS

`index.html` always served with:
```python
Cache-Control: no-cache, no-store, must-revalidate
Pragma: no-cache
Expires: 0
```
Prevents browser from caching old SPA shell after deploy.

---

*Tags: @CLIENT_PORTAL @CLIENT_AUTH @CLIENT_SUBS @CLIENT_DEVICES @CLIENT_APK @CLIENT_VERSION*
