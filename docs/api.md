# API Reference

The admin panel exposes a REST API at `http://YOUR_SERVER:10086/api/v1/`. All endpoints (except auth and a few public ones) require a Bearer token in the `Authorization` header.

Interactive API documentation is available at:
```
http://YOUR_SERVER:10086/api/docs
```

---

## Authentication

### Get a Token

```bash
POST /api/v1/auth/login
Content-Type: application/json

{"username": "admin", "password": "your-password"}
```

Response:

```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 86400
}
```

Use the token in all subsequent requests:

```bash
curl -H "Authorization: Bearer eyJ..." http://localhost:10086/api/v1/servers
```

Brute-force protection is active: after 5 failed attempts, the account is locked for 5 minutes.

---

## Servers

### List Servers

```bash
GET /api/v1/servers
```

### Get Server

```bash
GET /api/v1/servers/{id}
```

### Add Server

```bash
POST /api/v1/servers
Content-Type: application/json

{
  "name": "Amsterdam",
  "endpoint": "203.0.113.10:51820",
  "interface": "wg0",
  "server_type": "wireguard",
  "address_pool_ipv4": "10.66.66.0/24",
  "ssh_host": "203.0.113.10",
  "ssh_user": "root",
  "ssh_password": "secret"
}
```

### Install Agent

```bash
POST /api/v1/servers/{id}/install-agent
Content-Type: application/json

{"port": 8001}
```

### Reconcile Drift

Trigger drift detection and auto-reconciliation for a single server:

```bash
POST /api/v1/servers/{id}/reconcile
```

Response:

```json
{
  "server_id": 1,
  "server_name": "Amsterdam",
  "drift_detected": false,
  "issues": [],
  "reconciled": ["alice-laptop (PK1a2b3c...)"]
}
```

### Delete Server

```bash
DELETE /api/v1/servers/{id}
```

Add `?force=true` to remove even if the server is offline.

---

## Clients

### List Clients

```bash
GET /api/v1/clients
```

Query parameters:
- `server_id` — filter by server
- `status` — filter by status (`active`, `disabled`, `expired`)
- `search` — search by name

### Get Client

```bash
GET /api/v1/clients/{id}
```

### Create Client

```bash
POST /api/v1/clients
Content-Type: application/json

{
  "name": "alice-laptop",
  "server_id": 1,
  "expiry_date": "2026-12-31T00:00:00Z",
  "traffic_limit_mb": 51200,
  "bandwidth_limit": 50
}
```

### Download Client Config

```bash
GET /api/v1/clients/{id}/config
```

Returns the WireGuard `.conf` file as plain text.

### Enable / Disable Client

```bash
POST /api/v1/clients/{id}/enable
POST /api/v1/clients/{id}/disable
```

### Delete Client

```bash
DELETE /api/v1/clients/{id}
```

---

## Health Monitoring

### System Health

```bash
GET /api/v1/health/system
GET /api/v1/health/system?full=true   # includes external pings
POST /api/v1/health/system/refresh    # force refresh
```

### All Servers Health

```bash
GET /api/v1/health/servers
GET /api/v1/health/servers?full=true  # includes wg stats + system metrics
```

Response includes a `drift` field per server:

```json
{
  "servers": [
    {
      "server_id": 1,
      "server_name": "Amsterdam",
      "status": "healthy",
      "drift": {
        "detected": false,
        "details": null,
        "detected_at": null,
        "last_reconcile_at": "2026-03-15T10:00:00Z"
      }
    }
  ]
}
```

### Single Server Health

```bash
GET /api/v1/health/servers/{id}
POST /api/v1/health/servers/{id}/refresh
GET /api/v1/health/servers/{id}/history
```

---

## Updates

### Check Status

```bash
GET /api/v1/updates/status
```

Response:

```json
{
  "current_version": "1.1.0",
  "channel": "stable",
  "available_update": {
    "version": "1.2.0",
    "update_type": "minor",
    "changelog": "...",
    "has_db_migrations": true
  },
  "update_in_progress": false
}
```

### Apply Update

```bash
POST /api/v1/updates/apply
Content-Type: application/json

{"version": "1.2.0"}
```

### Check Progress

```bash
GET /api/v1/updates/progress/{update_id}
```

### Rollback

```bash
POST /api/v1/updates/rollback/{update_id}
```

### History

```bash
GET /api/v1/updates/history
```

### Change Channel

```bash
POST /api/v1/updates/channel
Content-Type: application/json

{"channel": "stable"}
```

---

## System

### Get Status

```bash
GET /api/v1/system/status
```

### Get Configuration

```bash
GET /api/v1/system/config
```

### Update Configuration

```bash
PATCH /api/v1/system/config
Content-Type: application/json

{"key": "backup_enabled", "value": "true"}
```

---

## Backup

### Create Backup

```bash
POST /api/v1/backup/create
```

### Download Backup

```bash
GET /api/v1/backup/download
```

Returns a `.tar.gz` archive.

### List Backups

```bash
GET /api/v1/backup/list
```

---

## Tariffs and Subscriptions

### List Plans

```bash
GET /api/v1/tariffs
```

### Create Plan

```bash
POST /api/v1/tariffs
Content-Type: application/json

{
  "name": "Basic",
  "price_month": 9.99,
  "traffic_limit_gb": 100,
  "duration_days": 30,
  "max_devices": 3
}
```

---

## Portal Users

### List Users

```bash
GET /api/v1/portal-users
```

### Get User

```bash
GET /api/v1/portal-users/{id}
```

### Manage Subscription

```bash
POST /api/v1/portal-users/{id}/subscription
Content-Type: application/json

{
  "action": "extend",
  "days": 30,
  "tier": "pro"
}
```

---

## Error Format

All errors return JSON:

```json
{
  "detail": "Human-readable error message"
}
```

| HTTP Status | Meaning |
|-------------|---------|
| 400 | Bad request — invalid parameters |
| 401 | Not authenticated — missing or invalid token |
| 403 | Forbidden — license tier insufficient |
| 404 | Not found |
| 409 | Conflict — e.g. another update is in progress |
| 422 | Validation error — request body schema mismatch |
| 500 | Internal error — check API logs |

---

## Rate Limiting

Login endpoint: 5 attempts per 5-minute window per IP.

There are no rate limits on other endpoints currently. In high-traffic deployments, put a reverse proxy (nginx) in front of the API.

---

## Complete API Documentation

The interactive Swagger UI at `/api/docs` documents every endpoint with request/response schemas, example values, and the ability to try requests directly in the browser.

ReDoc format is available at `/api/redoc`.
