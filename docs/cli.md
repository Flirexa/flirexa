# CLI Reference

`vpnmanager` is the official local operational interface for the product.

Supported operational usage:
- run as `root`
- or run via `sudo vpnmanager ...`

If a non-root user cannot read the product config, `vpnmanager` must fail cleanly and tell the operator to rerun with `sudo`.

## Public Commands

- `vpnmanager status`
- `vpnmanager health`
- `vpnmanager maintenance on --reason ...`
- `vpnmanager maintenance off`
- `vpnmanager license status`
- `vpnmanager services status`
- `vpnmanager services restart --api`
- `vpnmanager services restart --all --yes`
- `vpnmanager support-bundle --output <path> --redact-strict`
- `vpnmanager backup --full --output <path>`
- `vpnmanager backup --db-only --output <path>`
- `vpnmanager restore --archive <path> --yes`

## General Rules

- `--json` is the supported automation mode.
- Destructive commands require confirmation or `--yes`.
- Recovery commands remain usable in `license_expired_readonly`.
- Command and JSON freeze rules are documented in [cli-contract.md](cli-contract.md).

## Examples

```bash
sudo vpnmanager status
sudo vpnmanager health --json
sudo vpnmanager maintenance on --reason "planned maintenance"
sudo vpnmanager services restart --api
sudo vpnmanager support-bundle --output /tmp --redact-strict
sudo vpnmanager backup --full --output /tmp
sudo vpnmanager restore --archive /tmp/vpnmanager-backup-20260330-212008.tar.gz --yes
```

## Related Documents

- [cli-contract.md](cli-contract.md)
- [backup-restore.md](backup-restore.md)
- [disaster-recovery.md](disaster-recovery.md)
- [known-issues.md](known-issues.md)
