# Known Issues

This document lists currently known product issues for the commercial baseline line.

## 1. Early Installer Portal Warning

Symptom:
- installer verification may print:
  - `Client portal: not available (HTTP 000000)`

Observed behavior:
- the client portal may still become healthy shortly after install
- final `vpnmanager health` can be `ok`

Impact:
- cosmetic / UX only
- does not indicate a proven failed installation if post-install health is clean

Workaround:
- run:
  - `sudo vpnmanager health`
  - `sudo vpnmanager services status`

## 2. Transient Portal Warning After Full Services Restart

Symptom:
- `sudo vpnmanager services restart --all --yes` may return success with a temporary portal warning

Observed behavior:
- portal can still be in startup window when command prints result
- follow-up `vpnmanager health` becomes `ok`

Impact:
- minor operational UX issue
- not a confirmed service failure if follow-up health is clean

Workaround:
- wait a few seconds and rerun:
  - `sudo vpnmanager health`

## 3. Backup Block During Active Update Not Fully Reproducible Through Public CLI Alone

Symptom:
- in strict `install.sh + vpnmanager` testing, active update state is not easily inducible because there is no public `vpnmanager update` command

Impact:
- coverage gap in CLI-only validation
- not a confirmed runtime defect in backup logic itself

Operator note:
- update flow is still supported through the product update system and UI
- this item is documented so support does not treat it as an unexpected defect

## Support Rule

If a system is degraded or behavior looks inconsistent:
1. run `sudo vpnmanager status`
2. run `sudo vpnmanager health`
3. run `sudo vpnmanager support-bundle --output <path> --redact-strict`
4. attach the bundle to support
