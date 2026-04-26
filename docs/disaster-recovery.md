# Disaster Recovery Runbook

This is the supported administrator runbook for restoring the product without developer intervention.

Supported flow:

```text
old server -> full backup -> new server -> install -> restore -> verify
```

## Scope

This runbook applies to the supported commercial baseline:
- single-node self-hosted deployment
- Ubuntu Server 24.04 LTS or 22.04 LTS
- product-managed PostgreSQL
- product-managed systemd services

## What Restore Restores

Current supported restore scope:
- PostgreSQL application database
- `.env`
- local WireGuard / AmneziaWG config files included in backup
- product service restart
- post-restore health verification

Also restored indirectly through database content:
- servers
- clients
- update history stored in DB
- most product configuration stored in DB

## What Restore Does Not Guarantee Automatically

Not guaranteed automatically by current restore:
- SSL certificates reissue/reconfiguration
- external reverse proxy customizations
- arbitrary manual systemd unit edits
- arbitrary manual cron jobs
- manual out-of-band customizations outside product-managed files

## Prerequisites

Before disaster recovery, prepare:
- latest full backup archive
- current release archive
- root access to the new server
- DNS / domain access if public URLs are used
- saved license key / activation data

Important:
- keep the original backup archive name intact
- restore expects archive name format:
  - `vpnmanager-backup-<id>.tar.gz`

## Step 1. Create Full Backup On Old Server

Run on old server:

```bash
sudo vpnmanager backup --full --output /root/dr
```

Expected result:
- command returns `RESULT: SUCCESS`
- a full backup archive is created

Recommended additional diagnostic artifact:

```bash
sudo vpnmanager support-bundle --output /root/dr --redact-strict
```

## Step 2. Copy Backup Off The Old Server

Copy these to safe storage or directly to the new server:
- the full backup archive
- the support bundle (recommended)
- the release archive used for install

## Step 3. Prepare New Server

Create a clean supported Ubuntu server.

Verify:
- root access available
- enough disk space
- required ports/firewall/DNS ready

## Step 4. Install Product On New Server

On the new server:

```bash
tar xzf vpn-manager-v<version>.tar.gz
cd vpn-manager-v<version>
sudo bash install.sh --non-interactive
```

This prepares:
- `/opt/vpnmanager`
- `.env`
- PostgreSQL
- systemd units
- `vpnmanager` CLI
- base runtime layout

## Step 5. Copy Backup To New Server

Copy the original backup archive to the new server without renaming it.

Example target path:
- `/root/dr/vpnmanager-backup-<id>.tar.gz`

## Step 6. Restore On New Server

Run:

```bash
sudo vpnmanager restore --archive /root/dr/vpnmanager-backup-<id>.tar.gz --yes
```

Behavior:
- maintenance mode is enabled automatically if needed
- services are stopped
- DB is restored
- `.env` is restored
- local WireGuard configs are restored
- local PostgreSQL credentials are reconciled to restored `.env`
- services are restarted
- post-restore health is evaluated

## Step 7. Verify Recovery

Run:

```bash
sudo vpnmanager status
sudo vpnmanager health
sudo vpnmanager services status
sudo vpnmanager license status
```

Expected result:
- `status` is `SUCCESS`
- `health` is not `FAILED`
- API is healthy
- DB is connected
- Alembic matches head
- required services are active

## If Health Is Degraded

If `vpnmanager health` returns `DEGRADED`:
1. wait briefly and rerun health
2. run:
   - `sudo vpnmanager services status`
   - `sudo vpnmanager support-bundle --output /root/dr --redact-strict`
3. inspect known transient cases before escalating

## If Restore Failed

If restore returns `FAILED`:
1. do not start manual DB surgery
2. collect diagnostics:

```bash
sudo vpnmanager status
sudo vpnmanager health
sudo vpnmanager support-bundle --output /root/dr --redact-strict
```

3. inspect service logs if needed:

```bash
journalctl -u vpnmanager-api -u vpnmanager-client-portal -u vpnmanager-worker -n 100 --no-pager
```

4. send backup id, support bundle, and failure text to support

## Logs And Diagnostics

Useful sources:
- `sudo vpnmanager status`
- `sudo vpnmanager health`
- `sudo vpnmanager support-bundle --output <path> --redact-strict`
- `journalctl -u vpnmanager-api -u vpnmanager-client-portal -u vpnmanager-worker`

## After IP / Domain Change

If the new server has a different public IP or domain, verify:
- admin URL
- portal URL
- firewall rules
- customer-facing endpoints
- any client configs embedding old endpoint

If necessary:
- regenerate affected client configs
- reissue/reconfigure TLS externally

## Support Escalation Package

When contacting support, provide:
1. backup archive id
2. `sudo vpnmanager status`
3. `sudo vpnmanager health`
4. support bundle archive
5. brief symptom description
