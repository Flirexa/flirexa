# Ready To Sell Checklist

Commercial baseline target:
- First commercial release: `1.3.0`
- Current active commercial line: `1.4.x`

A release is ready to sell only when all items below are true on supported infrastructure.

## Installation

- [ ] clean install passes on fresh Ubuntu 24.04 VM
- [ ] `sudo vpnmanager status` works immediately after install
- [ ] `sudo vpnmanager health` works immediately after install
- [ ] CLI is present in `/usr/local/bin/vpnmanager`

## Update / Rollback

- [ ] update from previous supported version passes
- [ ] rollback passes on forced failure path
- [ ] post-update health is `SUCCESS` or explained `DEGRADED`
- [ ] `vpnmanager` remains present after update and rollback

## Backup / Restore / DR

- [ ] `sudo vpnmanager backup --full` creates valid archive
- [ ] `sudo vpnmanager backup --db-only` creates valid archive
- [ ] `verify_backup` passes on fresh archive
- [ ] `sudo vpnmanager restore --archive ... --yes` succeeds on supported host
- [ ] disaster recovery flow works: backup -> new server -> install -> restore -> health

## Diagnostics / Support

- [ ] `sudo vpnmanager support-bundle` creates archive
- [ ] support bundle redacts secrets
- [ ] support bundle contains status/health/update/log sections

## License / Modes

- [ ] license activation works
- [ ] `license_expired_readonly` still allows recovery commands
- [ ] maintenance mode works through CLI
- [ ] operational mode is visible in CLI and API

## Documentation

- [ ] installation docs match current installer behavior
- [ ] update docs match current runtime layout and channels
- [ ] backup/restore docs match current backend scope
- [ ] CLI docs match current command set and exit-code policy
- [ ] disaster recovery runbook is current

## Final Rule

If any of the following is missing, the product is not ready to sell:
- reproducible install
- reproducible update
- reproducible rollback
- reproducible backup
- reproducible restore
- reproducible disaster recovery
- usable diagnostics
- current docs
