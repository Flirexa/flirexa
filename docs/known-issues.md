# Known Issues

_Last verified: 2026-08-13._

This page contains current, actionable product behavior only. Historical
incidents and release notes live in Git and the changelog.

## 1. Portal startup warning during installation

The installer can report a client-portal warning while that service is still
starting. A final healthy result means the installation completed correctly.
If the warning remains, run:

```bash
sudo vpnmanager health
sudo vpnmanager services status
```

## 2. Brief portal warning after a full service restart

After `sudo vpnmanager services restart --all --yes`, wait a few seconds and
run `sudo vpnmanager health`. A healthy result means no further action is
required.

## 3. Legacy 2.2.59 archive activated but local panel is unlicensed

This applies only to a manually extracted legacy 2.2.59 archive. Do not request
another code or reset the existing one. Contact support with the activation
code and `vpnmanager license status`; support will provide the current
checksum-verified recovery command for the same machine.

## 4. Automatic end-customer renewal is temporarily unavailable

The client portal currently uses manual checkout/renewal. Existing signed
`auto_renewal` entitlements remain compatible, but the toggle and API stay
fail-closed until every extension can be tied to one newly verified provider
settlement. This does not change Flirexa monthly, annual, or Lifetime licence
purchases.

## 5. AmneziaWG availability depends on the operating-system release

The supported Ubuntu 22.04 LTS and 24.04 LTS profiles normally receive
WireGuard and AmneziaWG. A newer or otherwise unsupported OS may not have a
compatible AmneziaWG package repository yet. The installer reports this before
changing the host and requires explicit consent before continuing with
WireGuard only; it must not claim that AmneziaWG was installed.

For unattended installation, reduced protocol availability must be accepted
explicitly:

```bash
SB_ALLOW_WIREGUARD_ONLY=1 sudo bash install.sh --non-interactive
```

This flag does not make the detected OS part of the supported production
matrix.

## Support rule

For inconsistent or degraded behavior, collect:

```bash
sudo vpnmanager status
sudo vpnmanager health
sudo vpnmanager support-bundle --output /tmp --redact-strict
```

Attach the redacted bundle and exact error message to the support request.
