# Operations Runbook

This is the day-to-day operator and support runbook for the commercial product line.

## 1. Check System Status

```bash
sudo vpnmanager status
sudo vpnmanager health
sudo vpnmanager services status
sudo vpnmanager license status
```

Use these first before taking any recovery action.

## 2. Maintenance Mode

Enable maintenance:

```bash
sudo vpnmanager maintenance on --reason "planned maintenance"
```

Disable maintenance:

```bash
sudo vpnmanager maintenance off
```

Use maintenance mode before planned disruptive work.

## 3. Restart Services

Restart only API:

```bash
sudo vpnmanager services restart --api
```

Restart all managed services:

```bash
sudo vpnmanager services restart --all --yes
```

After restart, verify:

```bash
sudo vpnmanager health
```

## 4. Create Backup

Full backup:

```bash
sudo vpnmanager backup --full --output /root/backups
```

DB-only backup:

```bash
sudo vpnmanager backup --db-only --output /root/backups
```

Store backups outside the server as well.

## 5. Restore On The Same Server

```bash
sudo vpnmanager restore --archive /root/backups/vpnmanager-backup-<id>.tar.gz --yes
```

Then verify:

```bash
sudo vpnmanager status
sudo vpnmanager health
```

## 6. Restore On A New Server

1. copy release archive to new server
2. install product
3. copy backup archive with original name
4. run restore

```bash
tar xzf vpn-manager-v<version>.tar.gz
cd vpn-manager-v<version>
sudo bash install.sh --non-interactive
sudo vpnmanager restore --archive /root/backups/vpnmanager-backup-<id>.tar.gz --yes
sudo vpnmanager status
sudo vpnmanager health
```

## 7. Support Bundle

```bash
sudo vpnmanager support-bundle --output /root/support --redact-strict
```

Send the bundle together with:
- brief problem description
- timestamp of failure
- command output from `status` and `health`

## 8. What To Store Separately

Keep these outside the running server:
- full backup archives
- DB-only backup archives if used operationally
- support bundles for incidents
- commercial license key / activation data
- release archive used for install if needed for offline recovery

## 9. Where Logs Are

Primary logs:
- `journalctl -u vpnmanager-api`
- `journalctl -u vpnmanager-client-portal`
- `journalctl -u vpnmanager-worker`

Update logs:
- `.../backups/update_backups/.../apply.log`

## 10. Recovery Triage

### If `status = failed`
1. run `sudo vpnmanager health`
2. run `sudo vpnmanager services status`
3. collect support bundle

### If `health = failed`
1. inspect services
2. restart targeted service if justified
3. collect support bundle
4. if issue follows failed restore/update, use restore/rollback workflow

### If `restore failed`
1. do not hand-edit DB
2. collect support bundle
3. inspect journald
4. rerun only with clear reason, otherwise escalate

### If `update failed`
1. run `sudo vpnmanager status`
2. run `sudo vpnmanager health`
3. collect support bundle
4. inspect latest apply log
5. use documented rollback/update recovery path
