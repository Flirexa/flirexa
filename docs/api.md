# API reference

The Flirexa admin API is a documented FastAPI app. The fastest way to explore it is **Swagger UI**:

```
http://<your-server-ip>:10086/docs
```

This page is the conceptual companion: it explains the auth model, route grouping, and what to expect when calling paid endpoints from a FREE install.

---

## Authentication

### Admin API (`/api/v1/...`)

Admin endpoints require a JWT bearer token. To obtain one:

```bash
curl -X POST http://your-server:10086/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"your-password"}'
```

Response:

```json
{
  "access_token":  "eyJhbGciOi...",
  "refresh_token": "eyJhbGciOi...",
  "token_type":    "bearer",
  "expires_in":    1800
}
```

Pass the access token on subsequent requests:

```bash
curl http://your-server:10086/api/v1/clients \
  -H 'Authorization: Bearer eyJhbGciOi...'
```

Tokens expire in 30 minutes. Use the refresh token at `/api/v1/auth/refresh` to get a new access token without re-logging in.

### Client portal API (`/client-portal/...`)

End-user accounts use a separate JWT scope. The flow is the same — `POST /client-portal/auth/login` with the user's email and password — but the issued token only authorises portal endpoints, never the admin API.

### Internal service API (`/api/v1/internal/...`)

Service-to-service traffic between the admin API and the client portal uses a shared `SERVICE_API_TOKEN` from `.env` instead of JWT. End users never need to call these endpoints; they exist for the portal to reach the admin's client-creation logic without piggy-backing on user JWTs.

---

## Routes by domain

### Always available (FREE-friendly)

| Prefix | What it does |
|---|---|
| `/api/v1/auth` | Login, refresh, change password, manage admin accounts |
| `/api/v1/clients` | CRUD on VPN clients, configs, QR codes, traffic stats, expiry, limits |
| `/api/v1/servers` | List servers; create / start / stop / restart; reconcile drift; bootstrap; backup/restore. (Multi-server creation gated; agent install gated.) |
| `/api/v1/payments` | Subscription plans, payment providers status (gated by `payments` feature on URL prefix middleware) |
| `/api/v1/tariffs` | Tariff CRUD for the operator's pricing |
| `/api/v1/system` | License state, branding, SMTP, public IP, web access, audit logs, app logs |
| `/api/v1/health` | Quick + full system health checks |
| `/api/v1/portal-users` | End-user portal account management |
| `/api/v1/backup` | Manual backup, list, verify, restore, delete |
| `/api/v1/updates` | Check / apply / rollback updates; channel switching; restart |
| `/api/v1/internal` | Service-to-service endpoints (service token auth, not JWT) |
| `/api/v1/public` | Branding, login-page metadata (no auth) |

### Gated by license feature

These endpoints exist on every install but return **403** with a clear upgrade hint when the active license doesn't grant the required feature:

| Prefix / Endpoint | Gated by feature |
|---|---|
| `/api/v1/servers` POST creating Hysteria2/TUIC | `proxy_protocols` |
| `/api/v1/servers/{id}/install-agent`, `/discover` | `multi_server` |
| `/api/v1/agent/{id}/install`, `/uninstall`, `/switch-mode` | `multi_server` |
| `/api/v1/bots/client/start`, `/stop`, `/restart` | `telegram_client_bot` |
| `/api/v1/system/branding` POST, `/branding/logo` POST | `white_label_basic` |
| `/api/v1/system/backup-mount`, `/backup-unmount`, `/backup-test-write` | `auto_backup` |
| `/api/v1/traffic-rules` (whole router) | `traffic_rules` |
| `/api/v1/promo-codes` (whole router) | `promo_codes` |
| `/api/v1/app-accounts` (whole router) | `manager_rbac` |
| `/api/v1/corporate` and `/client-portal/corporate` (whole routers) | `corporate_vpn` |
| `/client-portal/create-invoice` with non-NOWPayments providers | provider-specific |

Sample 403 response:

```json
{
  "detail":  "This action requires the 'multi_server' feature. Current plan: free. Upgrade to enable it.",
  "status_code": 403
}
```

The plugin loader exposes `app.state.plugin_loader.loaded_features()` for clients that want to render UI conditionally without making a probe request.

### Plugin status

Each loaded paid plugin exposes a `GET /api/v1/plugins/<name>/status` endpoint (e.g. `/api/v1/plugins/multi-server/status`). On FREE installs these endpoints don't exist — the plugin shells aren't mounted.

---

## OpenAPI

The full OpenAPI 3.1 schema is available at:

```
http://your-server:10086/openapi.json
```

You can generate clients in any language with the standard OpenAPI generators. The schema reflects the active install — paid plugin endpoints appear in the schema only when the plugin is loaded.

---

## Common patterns

### Creating a client

```bash
curl -X POST http://your-server:10086/api/v1/clients \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "alice-laptop",
    "server_id": 1,
    "traffic_limit_gb": 100,
    "expiry_days": 30
  }'
```

The response includes an `id`, the generated WireGuard config as a string, and metadata. To download the `.conf` file or the QR code:

```
GET /api/v1/clients/{id}/config/download   →  binary .conf
GET /api/v1/clients/{id}/qrcode            →  PNG image
```

### Listing servers (paginated)

```bash
curl "http://your-server:10086/api/v1/servers?page=1&size=20" \
  -H "Authorization: Bearer $TOKEN"
```

### Health probe (no auth)

```bash
curl http://your-server:10086/health
```

Returns 200 with a small JSON `{"status": "ok", "version": "1.5.0"}` when the API process is up. Useful for upstream load balancer health checks.

---

## Webhooks (incoming)

Payment providers POST to dedicated webhook endpoints:

| Provider | Endpoint | Auth |
|---|---|---|
| NOWPayments | `/client-portal/webhooks/nowpayments` | HMAC-SHA512 over body, `x-nowpayments-sig` header |
| CryptoPay | `/client-portal/webhooks/cryptopay` | HMAC-SHA256 over body, `crypto-pay-api-signature` header |
| PayPal | `/client-portal/webhooks/paypal` | PayPal cert chain |
| Stripe (paid plugin) | `/webhooks/stripe` | Stripe signing secret |

All providers verify signatures and respond with 200 only after the subscription state has been persisted. Replay attempts on the same `payment_id` are idempotent — the second delivery sees the subscription already active and exits cleanly.

---

## Rate limits

There are no hard rate limits in 1.5.0. The admin API is intended to be used by operators (not end-users) and the client portal API has implicit limits via auth. We're tracking real-world usage and will add per-IP limits in a later release if abuse becomes an issue.

---

## Errors

Error responses follow FastAPI conventions:

```json
{ "detail": "Human-readable message" }
```

Status codes:

| Code | Meaning |
|---|---|
| 200 / 201 | Success |
| 400 | Bad request — validation error, missing fields, invalid IP |
| 401 | Not authenticated (missing or expired JWT) |
| 403 | Authenticated but not authorised — also returned for license-gated paid features |
| 404 | Resource doesn't exist |
| 409 | Conflict — duplicate name, etc. |
| 429 | Too many requests (currently only on auth login brute-force protection) |
| 500 | Internal error — file an issue with the request ID from `X-Request-ID` |
| 503 | License verification temporarily unavailable; retry shortly |

Every response carries an `X-Request-ID` header. Include it when reporting bugs — it lets us correlate with server-side logs immediately.
