# Backup and Restore

---

## Built-in Backup System

VPN Management Studio includes a scheduled backup system that runs in the background.

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

## Manual Backup

### Database

```bash
sudo -u postgres pg_dump vpnmanager_db > backup_$(date +%Y%m%d_%H%M).sql
```

If the database name is different (older installations may use `spongebot_db`), check `DATABASE_URL` in `.env`:

```bash
grep DATABASE_URL /opt/vpnmanager/.env
```

### WireGuard Configuration

```bash
sudo cp -r /etc/wireguard/ ~/wg_backup_$(date +%Y%m%d)/
sudo cp -r /etc/amneziawg/ ~/awg_backup_$(date +%Y%m%d)/   # if using AmneziaWG
```

### Application Configuration

```bash
cp /opt/vpnmanager/.env ~/env_backup_$(date +%Y%m%d)
```

### Full Application Directory

```bash
sudo tar czf ~/vpnmanager_full_backup_$(date +%Y%m%d).tar.gz \
  --exclude=/opt/vpnmanager/venv \
  --exclude=/opt/vpnmanager/src/web/frontend/node_modules \
  /opt/vpnmanager/
```

---

## Restore from Manual Backup

### Restore Database

```bash
sudo -u postgres psql -c "DROP DATABASE IF EXISTS vpnmanager_db;"
sudo -u postgres psql -c "CREATE DATABASE vpnmanager_db OWNER vpnmanager;"
sudo -u postgres psql vpnmanager_db < backup_20260101_0300.sql
```

### Restore Application Config

```bash
cp ~/env_backup_20260101 /opt/vpnmanager/.env
```

### Restart Services

```bash
systemctl restart vpnmanager-api
systemctl restart vpnmanager-worker
systemctl restart vpnmanager-client-portal
```

### Verify

```bash
curl http://localhost:10086/health
```

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

# Download backup archive
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:10086/api/v1/backup/download \
  -o backup.tar.gz
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
2. Extract the VPN Manager distribution package
3. Restore `.env` from backup to the new install directory
4. Run the installer — it detects the existing `.env` and uses those credentials:
   ```bash
   sudo bash install.sh --non-interactive
   ```
5. Restore the database from the latest dump
6. Restart all services
7. Verify via the admin panel

For remote servers: the agent will be reinstalled automatically when you next click **Install Agent** in the admin panel. The database already contains all peer configurations.
