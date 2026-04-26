# CLI Contract

This document freezes the public operational contract of `vpnmanager` for the commercial line. The baseline began in `1.3.0` and remains in force for the current `1.4.x` line.

## Scope

This contract applies to:
- `vpnmanager status`
- `vpnmanager health`
- `vpnmanager maintenance on/off`
- `vpnmanager license status`
- `vpnmanager services status`
- `vpnmanager services restart`
- `vpnmanager support-bundle`
- `vpnmanager backup`
- `vpnmanager restore`

The command names, destructive semantics, and JSON field families in this document must not be broken within the active commercial line without an explicit bugfix reason and release note.

## General Rules

- Supported operational usage is `sudo vpnmanager ...` or root.
- Non-root invocation must fail cleanly without traceback if required product config is unreadable.
- `--json` is the supported automation mode.
- Destructive commands require explicit confirmation via `--yes` or interactive confirmation.
- Recovery commands remain allowed in `license_expired_readonly`.

## Command Table

| Command | Type | Success Exit Code | Failure Exit Code | AuditLog | Notes |
|---|---|---:|---:|---|---|
| `vpnmanager status` | read-only | 0 | 1 | no | overall system state |
| `vpnmanager health` | read-only | 0 for `ok`/`degraded`, 1 for `failed` | 1 | no | health verdict command |
| `vpnmanager maintenance on --reason ...` | mutating | 0 | 1 | yes | explicit maintenance mode |
| `vpnmanager maintenance off` | mutating | 0 | 1 | yes | exits maintenance mode |
| `vpnmanager license status` | read-only | 0 | 1 only on command failure | no | readonly license state is not command failure |
| `vpnmanager services status` | read-only | 0 | 1 | no | service health view |
| `vpnmanager services restart --api` | mutating | 0 | 1 | yes | partial service restart |
| `vpnmanager services restart --all --yes` | mutating/destructive | 0 | 1 | yes | full managed service restart |
| `vpnmanager support-bundle ...` | read-only | 0 | 1 | no | diagnostic archive |
| `vpnmanager backup --full ...` | non-destructive operational write | 0 | 1 | yes | strict backup |
| `vpnmanager backup --db-only ...` | non-destructive operational write | 0 | 1 | yes | strict DB-only backup |
| `vpnmanager restore --archive ... --yes` | destructive | 0 | 1 | yes | strict restore |

## JSON Contract Rules

### Stable Rules

For the active commercial line (`1.4.x` at the time of writing):
- commands supporting `--json` must keep returning valid JSON
- top-level success/failure semantics must not invert
- command names and major field groups must remain stable
- additive fields are allowed
- silent removal or rename of established top-level fields is not allowed

### Command Families

`status` / `health` / `license status` / `services status` return the system status model, including these top-level fields:
- `collected_at`
- `result`
- `version`
- `mode`
- `maintenance_reason`
- `layout_mode`
- `install_root`
- `current_release`
- `services`
- `license`
- `update`
- `backup`
- `health`
- `disk`
- `uptime`
- `db`
- `degraded_reasons`
- `failed_reasons`

`maintenance on/off` returns:
- `success`
- `action`
- `mode`
- `reason`

`services restart` returns:
- `success`
- `action`
- `requested_scope`
- `restarted_units`
- `version`
- `mode`
- `health_summary`
- `warnings`
- `error`

`support-bundle` returns:
- `success`
- `archive_path`
- `bundle_size_bytes`
- `sections_included`
- `sections_failed`
- `manifest_path`

`backup` returns:
- `success`
- `action`
- `backup_type`
- `archive_path`
- `size_bytes`
- `version`
- `mode`
- `included_sections`
- `warnings`
- `error`

`restore` returns:
- `success`
- `action`
- `archive_path`
- `backup_id`
- `version`
- `mode`
- `restored_sections`
- `warnings`
- `error`
- `maintenance_reason`
- `health_summary`
- `log_hint`

## Success / Failed / Warning Semantics

### `status`
- success: command returns system summary
- failure: collector cannot produce a valid result
- warning/degraded: represented in `result=degraded` and reason arrays

### `health`
- success: `result=ok`
- warning: `result=degraded`
- failure: `result=failed`

### `license status`
- success: command executes and returns current license state
- warning: readonly or grace is represented in data, not exit code
- failure: only command execution failure

### `services restart`
- success: requested restart completed
- warning: command may return success with warnings if a component needs short stabilization
- failure: blocked or restart failed

### `backup`
- success: complete backup archive created
- warning: online snapshot warnings may be present while success remains true
- failure: any required backup section failed

### `restore`
- success: restore completed and post-restore verification passed under the command policy
- warning: degraded but recoverable post-restore observations may be surfaced in `warnings`
- failure: required restore step failed, verification failed, or confirmation missing

## Allowed Modes

| Command | normal | degraded | maintenance | update_in_progress | rollback_in_progress | license_expired_readonly |
|---|---|---|---|---|---|---|
| `status` | yes | yes | yes | yes | yes | yes |
| `health` | yes | yes | yes | yes | yes | yes |
| `license status` | yes | yes | yes | yes | yes | yes |
| `services status` | yes | yes | yes | yes | yes | yes |
| `services restart` | yes | yes | policy-limited | no | no | yes |
| `support-bundle` | yes | yes | yes | yes | yes | yes |
| `backup` | yes | yes | yes | no | no | yes |
| `restore` | yes | yes | auto-maintenance | no | no | yes |
| `maintenance on/off` | yes | yes | yes | policy-limited | policy-limited | yes |

## Freeze Rule

Within the active commercial line:
- do not break command names
- do not break destructive confirmation rules
- do not break top-level JSON shape
- do not change exit code meaning casually

Only real bugfixes justify contract changes, and they must be documented in release notes.
