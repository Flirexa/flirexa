# CLI Reference

The `vpnmanager` command is the primary CLI tool for managing your VPN Management Studio installation.

## Usage

```bash
vpnmanager <command> [options]
```

## Commands

### status

Display the overall system status including service health, active clients, and server load.

```bash
vpnmanager status
```

### health

Run a comprehensive health check across all components.

```bash
vpnmanager health
```

Example output:

```
[OK] Database connection
[OK] API service
[OK] Worker service
[OK] License valid
[OK] VPN protocols active
```

### backup

Create a full backup of the database, configuration, and keys.

```bash
vpnmanager backup
```

The backup archive is saved to the configured backup directory with a timestamped filename.

### restore

Restore from a previously created backup.

```bash
vpnmanager restore <backup-file>
```

### update

Check for and apply available updates.

```bash
vpnmanager update
```

The system will download and apply the latest update from the configured update channel (test or stable).

### rollback

Roll back to the previous version after an update.

```bash
vpnmanager rollback
```

### license status

Display current license information including tier, expiration, and hardware binding.

```bash
vpnmanager license status
```

Example output:

```
License tier:    Business
Status:          Active
Hardware ID:     a1b2c3d4e5f6
Activated:       2026-01-15
Last verified:   2026-04-18
```

### services status

Show the status of all managed services.

```bash
vpnmanager services status
```

### services restart

Restart all managed services or a specific service.

```bash
vpnmanager services restart
vpnmanager services restart <service-name>
```

### maintenance on/off

Enable or disable maintenance mode. When enabled, client connections are paused and the admin panel shows a maintenance banner.

```bash
vpnmanager maintenance on
vpnmanager maintenance off
```

### support-bundle

Generate a diagnostic bundle for support requests. The bundle includes logs, configuration (with secrets redacted), and system information.

```bash
vpnmanager support-bundle
```

The output archive can be attached to a support request at [support@flirexa.biz](mailto:support@flirexa.biz).

## JSON output

Most commands support JSON output for scripting and automation:

```bash
vpnmanager status --json
vpnmanager health --json
vpnmanager license status --json
vpnmanager services status --json
```
