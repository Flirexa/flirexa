# Getting Started

VPN Management Studio is a self-hosted platform for managing WireGuard and AmneziaWG VPN servers. It provides a web admin panel, a client self-service portal, Telegram bots, and a remote agent system — all in a single deployable package.

---

## What Is VPN Management Studio

You install it on a Linux server. It takes over the WireGuard configuration on that server and any remote servers you add. You manage everything from a single web interface: add clients, issue configs, monitor traffic, apply bandwidth limits, and automate subscription billing.

It is designed for:
- VPN resellers and operators running fleets of WireGuard servers
- Teams that need controlled, audited access to VPN config management
- Service providers offering VPN subscriptions with a self-service client portal

---

## Key Features

| Feature | Description |
|---------|-------------|
| Multi-server management | Manage unlimited remote WireGuard / AmneziaWG servers from one panel |
| Remote agent | Lightweight HTTP agent replaces SSH for day-to-day operations |
| Client portal | End-user web UI for self-registration, payment, and config download |
| Telegram bots | Admin bot for operations, client bot for self-service |
| Traffic & bandwidth | Per-client traffic counters, limits, and `tc`-based bandwidth shaping |
| Subscriptions | Plan-based billing with CryptoPay integration |
| Automatic updates | Signed update packages with rollback support |
| Backup and restore | Scheduled database + config backups with one-command restore |
| Drift detection | Automatic comparison of DB state vs live WireGuard interface with auto-reconcile |
| AmneziaWG support | Full support for obfuscated WireGuard with obfuscation parameters |
| White-label | Custom branding: name, logo, colors, domain |

---

## WireGuard vs AmneziaWG

VPN Management Studio supports both protocols transparently.

**WireGuard** is the standard protocol. It is fast, widely supported, and works out of the box on most clients. Use it by default.

**AmneziaWG** is an obfuscated variant of WireGuard that hides the VPN traffic signature. It is useful in environments where standard WireGuard is blocked by DPI firewalls. The server requires the `amneziawg-dkms` kernel module. Clients must use the AmneziaVPN app (available for Android, iOS, Windows, macOS).

When you add a server, you select the type: `wireguard` or `amneziawg`. All subsequent operations — peer management, config generation, health checks — handle the protocol differences automatically.

---

## Quick Start

**1. Install on a fresh server:**

```bash
tar xzf vpn-manager-v1.5.48.tar.gz
cd vpn-manager-v1.5.48
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

**4. Activate your license:**

Go to **Settings → License**, paste your activation code, click **Activate**.

Trial mode allows 10 clients on 1 server for 7 days.

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
