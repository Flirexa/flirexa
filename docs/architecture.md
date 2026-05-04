# Architecture

---

## Overview

VPN Management Studio is a multi-process Python application deployed on one or more Linux servers.

```
                     Internet
                        |
               [Firewall / NAT]
                        |
          +-------------+-------------+
          |             |             |
    :10086 (HTTP)  :10090 (HTTP)  :51820 (UDP)
    Admin Panel    Client Portal   WireGuard
          |             |             |
     [FastAPI]     [FastAPI]     [wg0/awg0]
          |             |
          +------+------+
                 |
           [PostgreSQL]
                 |
      [Background Worker]


     Remote Server 1          Remote Server N
     ┌───────────────┐        ┌───────────────┐
     │ FastAPI Agent │  ...   │ FastAPI Agent │
     │ :8001         │        │ :8001         │
     │ wg0 / awg0    │        │ wg0 / awg0    │
     └───────────────┘        └───────────────┘
```

---

## Components

### API Server (`vpnmanager-api`)

The main FastAPI application. Handles:
- Admin panel HTTP requests
- All `/api/v1/*` endpoints
- JWT authentication for admin users
- License validation middleware
- WireGuard operations for the local server
- Coordination of remote agent calls
- Background monitoring loop (when `WORKER_ENABLED=false`)

**Port:** 10086 (configurable via `API_PORT`)
**Process:** Uvicorn, 1 worker
**Tech:** Python 3.10+, FastAPI, SQLAlchemy, Alembic

---

### Client Portal (`vpnmanager-client-portal`)

A separate FastAPI process serving the client self-service portal.

Handles:
- Client user registration and login
- Subscription purchase and management
- VPN config download
- CryptoPay webhook processing

Communicates with the main API internally via `SERVICE_API_TOKEN`.

**Port:** 10090 (configurable via `CLIENT_PORTAL_PORT`)

---

### Background Worker (`vpnmanager-worker`)

A long-running Python process that handles time-based and event-based background work:

- Subscription expiry checks
- Traffic limit enforcement
- Automatic subscription renewal
- Scheduled backup creation
- Payment expiry cleanup
- Drift detection and reconciliation (every 5 minutes)

Running the worker as a separate service is recommended for production. If `WORKER_ENABLED=false`, the API process handles these tasks internally.

---

### Admin Bot (`vpnmanager-admin-bot`)

A Telegram bot for administrators. Reads and writes the same database as the API.

- Client management via Telegram commands
- Server status and alerts
- Traffic and subscription notifications

---

### Client Bot (`vpnmanager-client-bot`)

A Telegram bot for end users. Provides:
- Self-registration
- VPN config download and QR code
- Traffic usage and subscription status

---

### Remote Agent (`vpnmanager-agent`)

Runs on each remote WireGuard server. A minimal FastAPI app that:
- Executes `wg` / `awg` / `tc` / `ip` commands locally
- Exposes a REST API for peer management
- Runs in an isolated venv at `/opt/vpnmanager-agent/`

The main server communicates with agents over HTTP using per-server API keys.

---

## Database

PostgreSQL 15+. All state is stored in the database, including:
- Server and client records
- WireGuard public/private keys (encrypted at rest via SQLAlchemy column encryption)
- Subscription and payment records
- Update history
- Admin users and session data
- Health monitoring state
- Audit logs

**Key tables:**

| Table | Description |
|-------|-------------|
| `servers` | WireGuard server records, SSH/agent credentials, drift state |
| `clients` | VPN peer records, keys, IPs, traffic counters |
| `client_users` | Portal user accounts |
| `subscriptions` | Active and historical subscription records |
| `payments` | Payment records per invoice |
| `update_history` | All update and rollback operations |
| `system_config` | Key/value store for admin panel settings |
| `audit_logs` | Admin action audit trail |

Migrations are managed with Alembic. The migration chain runs automatically on startup.

---

## Request Flow: Adding a Client

```
Admin → POST /api/v1/clients
           │
           ▼
     auth middleware (JWT)
           │
           ▼
     license middleware (tier check)
           │
           ▼
     clients.py route handler
           │
           ├── assign IP from address pool
           ├── generate key pair
           ├── write to DB
           │
           ▼
     ServerManager._get_wg(server)
           │
           ├── agent mode → AgentClient.peer_create(pubkey, allowed_ips)
           │                    └── POST http://remote:8001/peer/create
           │
           └── ssh mode → WireGuardManager.add_peer(pubkey, allowed_ips)
                              └── ssh → wg set wg0 peer ...
```

---

## Request Flow: Drift Detection

Every 5 minutes the worker (or API background loop) runs `run_reconciliation()`:

```
for each ONLINE server:
    │
    ├── get live peers from interface (via agent or SSH)
    │       └── wg show dump → list of public keys
    │
    ├── get expected peers from DB
    │       └── SELECT * FROM clients WHERE server_id=X AND enabled=true
    │
    ├── compare sets
    │
    ├── missing from live (safe drift):
    │       └── wg set {iface} peer {pubkey} allowed-ips {ip}
    │
    └── interface down / agent unreachable (unsafe drift):
            └── server.drift_detected = True
                server.drift_details = {issues: [...]}
```

---

## Update System

```
Admin panel → POST /api/v1/updates/apply
                    │
                    ▼
              validation (version, disk, lock)
                    │
                    ▼
              download package → verify SHA-256
                    │
                    ▼
              create backup (code + DB dump)
                    │
                    ▼
              update_apply.sh
                  S0: disk preflight
                  S3: backup (code tar + pg_dump)
                  S4: stop services
                  S5: extract package
                  S6: pip install -r requirements.txt
                  S7: alembic upgrade head
                  S8: start services
                  S9: smoke check (GET /health)
                  S10: verify VERSION
                    │
              smoke check passes → success
              smoke check fails  → rollback from backup
```

---

## Security Model

**Authentication:**
- Admin panel: JWT Bearer tokens (HS256, configurable expiry)
- Client portal: separate JWT with longer expiry
- Agent API: per-server API key in `X-Api-Key` header

**Encryption at rest:**
- WireGuard private keys encrypted in the database
- SSH passwords encrypted in the database
- Agent API keys encrypted in the database
- Encryption key derived from `VMS_ENCRYPTION_KEY` env var or `/etc/machine-id`

**License protection:**
- RSA-PSS signed license keys
- Online validation via license server (72-hour grace period)
- License server URL signed separately — cannot be tampered with in a distributed package

**Update integrity:**
- Update packages signed with RSA-PSS
- SHA-256 checksum verified after download
- Package URL embedded in the signed manifest — URL injection is not possible

**Code integrity:**
- Sentinel process checks SHA-256 of critical files on startup and every 200 requests
- License module protected with PyArmor obfuscation in production builds

---

## Technology Stack

| Layer | Technology |
|-------|-----------|
| API framework | FastAPI |
| ORM | SQLAlchemy 2.x |
| Migrations | Alembic |
| Database | PostgreSQL 15+ |
| Frontend | Vue 3 + Vite + Bootstrap 5 |
| HTTP client | httpx |
| SSH | Paramiko |
| Telegram | python-telegram-bot |
| Process manager | systemd |
| VPN | WireGuard / AmneziaWG |
| Traffic shaping | `tc` (Linux traffic control) |
