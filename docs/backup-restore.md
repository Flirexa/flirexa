# Backup and Restore

_Last verified: 2026-08-13._

---

## Built-in Backup System

Manual full/database backups and restores are available on FREE. Scheduled
backups, retention settings, and managed network storage require the Business+
`auto-backup` feature.

You can also run backups and restores from the CLI: `vpnmanager backup --full` (or `--db-only`) and `vpnmanager restore --archive <path> --yes`. See [cli.md](cli.md).

### Configure Scheduled Backups

1. Go to **Settings → Backups** in the admin panel
2. Set:
   - **Enabled** — toggle backups on or off
   - **Interval** — how often to run (e.g. every 24 hours)
   - **Time (UTC)** — hour of day to run the backup
   - **Retention** — how many backups to keep (older ones are deleted automatically)
   - **Storage type** — local directory or mounted network share

Each backup includes:
- Full PostgreSQL database dump
- WireGuard configuration files from `/etc/wireguard/` and `/etc/amneziawg/`
- The `.env` file

### Storage Options

**Local storage** (default): backups are written to `{install_dir}/backups/` or a custom path.

**Network share** (SMB/NFS): mount a network share and point the backup system at the mount point. The system writes the same backup files there.

---

## Manual backup

Use the product CLI so metadata and checksums are included:

```bash
sudo vpnmanager backup --full --output /var/backups/flirexa
sudo vpnmanager backup --db-only --output /var/backups/flirexa
```

A current full archive is named `vpnmanager-backup-<backup_id>.tar.gz` and uses
the `tar.gz/v2` format. It includes a compressed PostgreSQL dump, `.env`, local
WireGuard/AmneziaWG configuration, per-server exports, product version, metadata,
and checksums. Store a copy off the application host.

Archive creation is serialized across the admin API, scheduler, CLI, and
worker. If one backup is already running, another request receives a clear busy
response instead of starting a second dump or racing retention. The mobile
admin view also keeps the create action disabled with visible progress while
the request is running.

On phones and tablets, Archives, Schedule, and Storage are separate compact
views. Archive rows keep date, size, type, and verification state readable;
verify, restore, database-only restore, and delete actions open in a focused
bottom sheet rather than a horizontally compressed desktop table.

## Restore

Restore is destructive. Confirm that you have the intended archive and a separate
copy before running:

```bash
sudo vpnmanager restore \
  --archive /var/backups/flirexa/vpnmanager-backup-<backup_id>.tar.gz \
  --yes
```

The restore command verifies the archive, restores the database, `.env`, and local
VPN configuration, restarts product services, and evaluates health. It does not
restore TLS certificates, custom reverse-proxy configuration, remote agent
installations, or out-of-band system customizations.

---

## Rollback via Update History

If a recent **update** caused problems, the update system maintains its own pre-update backup (code + database dump) stored at:

```
{install_dir}/backups/update_backups/pre_{version}_{timestamp}/
```

To restore from an update backup:

**Via the admin panel:**
1. Go to **Updates → History**
2. Find the update record with a backup available (green badge)
3. Click **Rollback**

**Via the command line:**

```bash
cd /opt/vpnmanager
sudo bash update.sh --rollback
```

This restores both the code and the database from the most recent update backup, then restarts all services and runs a smoke check.

---

## Backup via the Admin Panel API

You can trigger a backup on demand via the API:

```bash
# Trigger backup
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  http://localhost:10086/api/v1/backup/create

# List and verify archives already stored on the server
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:10086/api/v1/backup/list
curl -X POST -H "Authorization: Bearer $TOKEN" \
  http://localhost:10086/api/v1/backup/verify/BACKUP_ID
```

---

## What Is Not Backed Up

- Python virtual environment (`venv/`) — recreated from `requirements.txt` on restore
- Frontend build artifacts (`src/web/static/dist/`) — rebuilt during install/update
- Agent installations on remote servers — the agent is reinstalled automatically when needed

Remote server WireGuard configs are stored in the database and can be re-pushed to remote agents at any time.

---

## Disaster Recovery Checklist

If the server is lost and you need to rebuild from scratch:

1. Provision a new server with the same OS
2. Install the same supported Flirexa product generation
3. Copy the full backup archive to the new host
4. Run `sudo vpnmanager restore --archive <archive> --yes`
5. Re-provision TLS/reverse-proxy configuration and any remote agents
6. Verify `/health`, the admin panel, VPN interfaces, and a test client

For remote servers: the agent will be reinstalled automatically when you next click **Install Agent** in the admin panel. The database already contains all peer configurations.
