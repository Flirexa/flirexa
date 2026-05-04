# Updates

VPN Management Studio has a built-in update system with cryptographically signed packages, channel-based distribution, and automatic rollback on failure.

---

## How It Works

1. A signed manifest is published to an update channel (`stable` or `test`)
2. The admin panel polls the channel every few minutes and shows available updates
3. You trigger the update from the **Updates** page in the admin panel
4. The system downloads the package, verifies its SHA-256 checksum, creates a backup, applies the update, runs migrations, restarts services, and runs a smoke check
5. If anything fails, it automatically rolls back from the backup

All update packages are signed with an RSA-PSS key. The corresponding public key ships with the distribution. A package with an invalid signature is rejected before download. Package downloads require a valid license key — unauthorized access is rejected with HTTP 403.

---

## Update Channels

| Channel | Description |
|---------|-------------|
| `stable` | Production releases, fully tested and promoted from `test` |
| `test` | Release candidates — all new builds go here first |

The active channel is shown on the **Updates** page. Switch channels in **Settings → Update Channel** or via the API:

```bash
POST /api/v1/updates/channel
{"channel": "stable"}
```

---

## Release Workflow

All new versions follow a **test → stable** promotion cycle:

```
build_release.sh
       ↓
  publish to TEST channel
       ↓
  apply update on test stand, verify everything works
       ↓
  promote to STABLE channel  ←  clients on stable receive the update
```

### Step by step (developer)

1. Make code changes and commit
2. Bump version in `VERSION` file
3. Run `bash build_release.sh`
4. Publish to **test** channel via the license server admin panel (`/panel/updates`)
5. On your test server, switch to `test` channel and apply the update via admin panel
6. Run through the test checklist (see below)
7. If all checks pass, promote to stable via the license server admin panel

### Test Checklist

- [ ] Admin panel loads, login works
- [ ] Client portal loads
- [ ] WireGuard peers listed correctly
- [ ] Agent install works on a test server
- [ ] Client bot responds to /start
- [ ] Payment flow (if payment-related changes)
- [ ] Smoke check passes (green in Updates → History)

---

## Applying an Update

1. Go to **Updates** in the admin panel
2. If a new version is available, the version number and changelog are shown
3. Click **Apply Update**
4. Progress is shown in real time: download → backup → extract → migrate → restart → smoke check
5. On success: the new version is running
6. On failure: the system rolls back automatically and shows the error

### Service Restart Banner

After a successful update, a **Restart Required** banner appears. When you click **Restart Services**:

- A yellow warning banner immediately shows: **"Services are restarting…"**
- A 20-second countdown is displayed so you know approximately when the panel will respond again
- The frontend automatically polls every 2 seconds and removes the banner as soon as the API is back online
- You do not need to manually refresh — the page recovers on its own

The update is protected by an exclusive lock — only one update can run at a time. Concurrent requests are rejected with a clear error.

### Pre-flight Checks

Before downloading, the system verifies:
- At least 500 MB of free disk space in the install directory
- At least 200 MB of free space in `/tmp`
- No other update is currently in progress (checked both in memory and in the database)
- The new version is newer than the current version (no downgrade)

---

## Update History

Go to **Updates → History** to see all past updates:

- Version transitions (from → to)
- Status: success, failed, rolled back
- Duration
- Whether a rollback backup is still available

---

## Rollback

If you want to manually roll back to the previous version:

1. Go to **Updates → History**
2. Find the last successful update with a backup available (indicated by a green badge)
3. Click **Rollback**

The rollback:
- Restores the code from the pre-update backup archive
- Restores the database from the pre-update PostgreSQL dump
- Restarts all services
- Runs a smoke check

Rollback is also triggered automatically if the update smoke check fails.

### Smoke Check

After applying an update (or rollback), the system checks:
- `GET /health` on the API returns HTTP 200 (required — update fails if this fails)
- Worker systemd service is active (required)
- Client portal and bots are running (optional, warning only)

---

## Manual Update via Script

In addition to the UI-based mechanism, you can update manually:

```bash
cd /opt/vpnmanager
sudo bash update.sh
```

Options:

```bash
sudo bash update.sh --no-build     # Skip frontend rebuild (faster)
sudo bash update.sh --rollback     # Restore from latest backup
```

Or by re-running the installer with a new package:

```bash
tar xzf vpn-manager-v1.2.0.tar.gz
cd vpn-manager-v1.2.0
sudo bash install.sh
```

The installer detects an existing installation and performs a safe upgrade instead of a fresh install.

---

## Concurrent Update Protection

The update mechanism uses two layers of protection against concurrent runs:

1. **In-memory lock** — a flag set when an update task starts, cleared when it ends
2. **Database guard** — a query that checks for any record in `DOWNLOADING` or `APPLYING` state

If the server restarts mid-update (power loss, OOM), the database record stays in an incomplete state. On next startup, the API automatically marks these orphaned records as `FAILED` and clears the lock, allowing a new update to proceed.

---

## Security

### Package Download Protection

Update packages are not publicly downloadable. The download endpoint requires the instance's license key (`X-License-Key` header). The key is sent automatically by the update manager — no manual configuration needed.

The `package_url` field is present in the signed manifest (it is part of the cryptographic payload and cannot be tampered with), but it is never displayed in the admin panel or progress logs. Progress logs show only human-readable status messages.

### Manifest Integrity

Every manifest is signed with RSA-PSS-SHA256. The update manager verifies the signature using `data/update_public.pem` before proceeding. A tampered or forged manifest is rejected before any download starts.

---

## Troubleshooting Updates

**"Manifest signature invalid"**
The `update_public.pem` key on the server does not match the key used to sign the manifest. Make sure the file is at `{install_dir}/data/update_public.pem`.

**"Not enough disk space"**
Free up disk space before updating. The update needs 500 MB for the backup plus the package size.

**"Another update is in progress"**
Check the **Updates → History** page. If a record is stuck in `in_progress`, it was likely interrupted. Restart the API service to trigger orphan cleanup:

```bash
systemctl restart vpnmanager-api
```

**Update applied but services not restarting**
The `update_apply.sh` script uses service names from the current installation (e.g., `vpnmanager-api`). If your services have different names (older installations may use `spongebot-api`), the script logs a warning but the smoke check still passes if the API responds. The services are typically started by the old systemd units.

**Smoke check failed after update**
The system rolled back automatically. Check the update log in the history view for the specific error. Fix the root cause, then retry the update.
