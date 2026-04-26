# Backup and Restore

## Backup Contract

Current commercial baseline backup format:
- archive: `vpnmanager-backup-<backup_id>.tar.gz`
- format version: `tar.gz/v2`
- metadata file: `backup/metadata.json`

### Required Files In Full Backup

A valid full backup includes:
- `backup/metadata.json`
- `backup/database.sql.gz`
- `backup/system/version.txt`

Common additional files in a full backup:
- `backup/env.env`
- `backup/wireguard/*.conf`
- `backup/servers/*.json`
- `backup/servers/wg_config_*.conf`

### DB-Only Backup

A valid DB-only backup includes:
- `backup/metadata.json`
- `backup/database.sql.gz`
- `backup/system/version.txt`

## What `verify_backup` Checks

`verify_backup` checks:
- archive is readable
- `backup/` directory exists
- `metadata.json` exists and parses
- payload file checksums match metadata
- `database.sql.gz` exists and is not suspiciously small

## Official Backup Commands

Full backup:

```bash
sudo vpnmanager backup --full --output /tmp
```

DB-only backup:

```bash
sudo vpnmanager backup --db-only --output /tmp
```

## Backup Safety Policy

Backup is allowed in normal mode.

If maintenance mode is not enabled:
- backup still runs
- CLI warns that this is an **online snapshot**

Backup is blocked when:
- update is in progress
- rollback is in progress
- database is unavailable
- destination is not writable
- disk space is insufficient

## What Full Backup Currently Includes

Guaranteed current scope:
- PostgreSQL dump
- `.env`
- local WireGuard / AmneziaWG config files
- per-server exports and related server config snapshots
- backup metadata and version file

## Official Restore Command

```bash
sudo vpnmanager restore --archive /path/to/vpnmanager-backup-<id>.tar.gz --yes
```

or:

```bash
sudo vpnmanager restore --from-dir /path/to/backup-dir --yes
```

Restore is destructive.

## Current Restore Scope

Current restore guarantees restoration of:
- database
- `.env`
- local WireGuard / AmneziaWG config files
- local PostgreSQL credentials needed by the restored `.env`
- product service restart
- post-restore health evaluation

Current restore does **not** guarantee restoration of:
- SSL certificates
- nginx/custom reverse-proxy config
- remote agent installations on other nodes
- manual out-of-band customizations outside product-managed files

## Restore On A New Server

Official disaster recovery path is documented in [disaster-recovery.md](disaster-recovery.md).

Short version:
1. create full backup on old server
2. provision new supported Ubuntu server
3. install the same supported product generation
4. run `sudo vpnmanager restore --archive ... --yes`
5. verify health
