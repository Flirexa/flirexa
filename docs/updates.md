# Updates

## Update Model

VPN Management Studio uses a signed package update system with:
- update channels: `test` and `stable`
- signed manifest
- package checksum verification
- pre-update backup
- post-apply health checks
- rollback on failure

The runtime layout is:

```text
/opt/vpnmanager/
  current -> releases/<version>
  releases/
  staging/
  backups/
  update-lock/
```

## Commercial Release Lines

- `1.2.x` — pre-release / hardening / test line
- `1.3.x` — first commercial release line
- `1.4.x` — current active commercial line

Commercial baseline starts at:
- `1.3.0`

## Update Channels

| Channel | Purpose |
|---|---|
| `test` | release validation and pre-production verification |
| `stable` | customer production channel |

Recommended workflow:
1. publish to `test`
2. validate on real installed system / clean VM
3. only then promote to `stable`

## Applying Updates

Preferred path:
1. open admin panel
2. go to `Updates`
3. select channel
4. apply update
5. watch progress
6. verify post-update health

Post-update verification commands:

```bash
sudo vpnmanager status
sudo vpnmanager health
sudo vpnmanager services status
sudo vpnmanager license status
```

## Rollback

Rollback may be:
- automatic after failed update health check
- manual from the update subsystem

Rollback restores:
- code/runtime from previous release or pre-update backup
- database from pre-update dump when required
- services via restart

## Where To Look During Update Troubleshooting

Primary locations:
- `sudo vpnmanager status`
- `sudo vpnmanager health`
- `journalctl -u vpnmanager-api`
- latest `apply.log` under `backups/update_backups/.../apply.log`

Recommended triage sequence:

```bash
sudo vpnmanager status
sudo vpnmanager health
sudo vpnmanager services status
sudo vpnmanager support-bundle --output /tmp --redact-strict
```

## If Update Looks Stuck

1. Check current system state:

```bash
sudo vpnmanager status
sudo vpnmanager health
```

2. Check services:

```bash
sudo vpnmanager services status
```

3. If API is healthy but UI is stale, restart services carefully:

```bash
sudo vpnmanager services restart --api
```

or, if really needed:

```bash
sudo vpnmanager services restart --all --yes
```

4. Collect diagnostics:

```bash
sudo vpnmanager support-bundle --output /tmp --include-journal --include-update-logs --redact-strict
```
