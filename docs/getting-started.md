# Getting Started

_Last verified: 2026-07-24._

Flirexa is a self-hosted platform for managing WireGuard, AmneziaWG, and
licence-gated proxy protocols. It provides a web admin panel, a client
self-service portal, Telegram bots, and Business+ remote-node management.

---

## What Is Flirexa

You install it on a Linux server. It takes over the WireGuard configuration on that server and any remote servers you add. You manage everything from a single web interface: add clients, issue configs, monitor traffic, apply bandwidth limits, and automate subscription billing.

It is designed for:
- VPN resellers and operators running fleets of WireGuard servers
- Teams that need controlled, audited access to VPN config management
- Service providers offering VPN subscriptions with a self-service client portal

---

## Key Features

| Feature | Description |
|---------|-------------|
| Multi-server management (paid) | Manage remote nodes from one panel — Business tier; FREE runs two local protocol endpoints on one host |
| Remote agent (paid) | Separately delivered HTTP agent replaces SSH for day-to-day operations |
| Client portal | End-user web UI for self-registration, payment, and config download |
| Telegram bots | Admin bot for operations, client bot for self-service |
| Traffic & bandwidth | Per-client traffic counters, limits, and `tc`-based bandwidth shaping |
| Subscriptions | Plan-based billing with built-in NOWPayments (crypto) integration |
| Automatic updates | Signed manifest, checksum-verified package, and rollback support |
| Backup and restore | Manual backup/restore on FREE; scheduled backups on Business+ |
| Drift detection | Automatic comparison of DB state vs live WireGuard interface with auto-reconcile |
| AmneziaWG support | Full support for obfuscated WireGuard with obfuscation parameters |
| White-label | Custom branding: name, logo, colors, domain |

---

## WireGuard vs AmneziaWG

Flirexa supports both protocols transparently.

**WireGuard** is the standard protocol. It is fast, widely supported, and works out of the box on most clients. Use it by default.

**AmneziaWG** is an obfuscated variant of WireGuard that hides the VPN traffic signature. It is useful in environments where standard WireGuard is blocked by DPI firewalls. The server requires the `amneziawg-dkms` kernel module. Clients must use the AmneziaVPN app (available for Android, iOS, Windows, macOS).

When you add a server, you select the type: `wireguard` or `amneziawg`. All subsequent operations — peer management, config generation, health checks — handle the protocol differences automatically.

---

## Quick Start

**1. Install on a fresh server:**

```bash
curl -fsSL https://flirexa.biz/install.sh | sudo bash
```

Or from source:

```bash
git clone https://github.com/Flirexa/flirexa.git
cd flirexa
sudo bash install.sh
```

**2. Open the admin panel:**

```
http://YOUR_SERVER_IP:10086
```

Create your admin account on first visit.

**3. Open the client portal** (your end-users access this):

```
http://YOUR_SERVER_IP:10090
```

**4. Activate your license (optional):**

Go to **Settings → License**, paste your activation code or licence key, and click
**Activate**.

No licence is required. Without one the runtime uses **FREE** — 80 clients, one
host with WireGuard and AmneziaWG local endpoints, no expiry, and no licence
heartbeat. The installer and updater still contact official Flirexa services;
installer diagnostics can be disabled with `INSTALL_TELEMETRY=off`.

**5. Add your first client:**

Go to **Clients → Add Client**, enter a name, select the server, click **Create**.

Download the `.conf` file or scan the QR code with the WireGuard mobile app.

---

## Setting Up Domains (Recommended)

By default both panels are accessible by IP and port. To bind them to domains with HTTPS:

**During installation** — the installer asks interactively and offers two options:

- **Option 1:** Client portal on its own domain (Let's Encrypt) + admin panel via IP with self-signed TLS
- **Option 2:** Both panels on separate domains with Let's Encrypt certificates

Just answer the prompts — the installer handles nginx config and certificate issuance automatically.

To pre-configure for non-interactive installs:

```bash
# Option 1: portal on domain, admin by IP
export SB_WEB_SETUP_MODE=portal_admin_ip
export SB_CLIENT_PORTAL_DOMAIN=portal.yourdomain.com
export SB_CERTBOT_EMAIL=your@email.com
sudo -E bash install.sh --non-interactive

# Option 2: both on domains
export SB_WEB_SETUP_MODE=portal_admin_domain
export SB_CLIENT_PORTAL_DOMAIN=portal.yourdomain.com
export SB_ADMIN_PANEL_DOMAIN=admin.yourdomain.com
export SB_CERTBOT_EMAIL=your@email.com
sudo -E bash install.sh --non-interactive
```

**After installation** — via the admin panel:

Go to **Settings → Web Access** → enter your domains → click **Apply**. SSL certificates are issued automatically via Let's Encrypt.

Or via command line:

```bash
cd /opt/vpnmanager
sudo bash scripts/configure-web-access.sh \
  --mode portal_admin_domain \
  --admin-domain admin.yourdomain.com \
  --portal-domain portal.yourdomain.com \
  --email your@email.com
```

> **Requirements:** DNS A-records for both domains must already point to your server IP. Ports 80 and 443 must be open.

After setup:
- Admin panel → `https://admin.yourdomain.com`
- Client portal → `https://portal.yourdomain.com`

---

## What Happens Next

- [Installation details →](installation.md)
- [Adding remote servers →](add-server.md)
- [Managing clients →](client-management.md)
- [Update mechanism →](updates.md)
- [Full architecture overview →](architecture.md)
