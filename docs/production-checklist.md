# Production Checklist

Use this checklist before handing the system to a customer or declaring an installation production-ready.

## Server And Network

- [ ] Server uses supported OS: Ubuntu Server 24.04 LTS or 22.04 LTS
- [ ] Deployment is single-node control plane
- [ ] Server resources meet minimum requirements
- [ ] Public IP is assigned
- [ ] Required ports are open
- [ ] Firewall is configured
- [ ] DNS is configured if public domains are used
- [ ] Admin/client URLs point to the correct server

## Installation

- [ ] Release archive copied to server
- [ ] `bash install.sh --non-interactive` completed successfully
- [ ] `/usr/local/bin/vpnmanager` exists
- [ ] `sudo vpnmanager status` returns `SUCCESS`
- [ ] `sudo vpnmanager health` does not return `FAILED`

## Product Runtime

- [ ] API service is active
- [ ] client portal service is active
- [ ] worker service is active if expected
- [ ] PostgreSQL is active
- [ ] WireGuard interface is up if local VPN mode is used

## License

- [ ] License key is activated or activation plan is documented
- [ ] License key is stored securely by operator
- [ ] `sudo vpnmanager license status` returns expected state

## Backup And Recovery

- [ ] `sudo vpnmanager backup --full --output <path>` succeeds
- [ ] Full backup archive is copied to safe storage
- [ ] `sudo vpnmanager backup --db-only --output <path>` succeeds
- [ ] Restore procedure has been tested at least once
- [ ] Disaster recovery procedure has been tested at least once on fresh server

## Diagnostics

- [ ] `sudo vpnmanager support-bundle --output <path> --redact-strict` succeeds
- [ ] Support bundle location is documented for operator
- [ ] Operator knows where update/apply logs live
- [ ] Operator knows how to collect journald logs for product services

## Operations

- [ ] Operator knows `vpnmanager maintenance on/off`
- [ ] Operator knows `vpnmanager services restart`
- [ ] Operator knows `vpnmanager status` and `vpnmanager health`
- [ ] Operator knows restore procedure
- [ ] Operator knows support escalation path

## Monitoring And Support Readiness

- [ ] Basic host monitoring is enabled
- [ ] Disk space monitoring is enabled
- [ ] Service state monitoring is enabled
- [ ] Backup retention/storage policy is defined
- [ ] Support contact process is documented

## Final Gate

The system is production-ready only if all critical items above are complete and the operator can perform:
- install verification
- health verification
- backup creation
- support bundle collection
- restore or DR recovery according to the documented runbook
