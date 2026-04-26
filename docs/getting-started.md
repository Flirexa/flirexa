# Getting Started

VPN Management Studio is a self-hosted single-node VPN operations product.

The first commercial release was `1.3.0`. The current supported commercial line is `1.4.x`.

## What You Install

A fresh install gives you:
- admin panel
- client portal
- local `vpnmanager` CLI
- PostgreSQL-backed control plane
- systemd-managed services
- backup/restore workflow
- update/rollback workflow

## Quick Start

### 1. Install On A Fresh Supported Server

```bash
tar xzf vpn-manager-v<version>.tar.gz
cd vpn-manager-v<version>
sudo bash install.sh
```

### 2. Verify The System Locally

```bash
sudo vpnmanager status
sudo vpnmanager health
```

Expected:
- `status` succeeds
- `health` is not `FAILED`

### 3. Open The Admin Panel

Default direct URL:

```text
http://YOUR_SERVER_IP:10086
```

Create the first admin account on first visit.

### 4. License

If no activation code was provided during install, the product stays in `not_activated` state until the operator activates it.

Check current license state:

```bash
sudo vpnmanager license status
```

### 5. First Operator Checks

Recommended first checks:

```bash
sudo vpnmanager services status
sudo vpnmanager support-bundle --output /tmp --redact-strict
```

## What To Read Next

- [installation.md](installation.md)
- [cli.md](cli.md)
- [backup-restore.md](backup-restore.md)
- [disaster-recovery.md](disaster-recovery.md)
- [operations-runbook.md](operations-runbook.md)
