# Release Notes — 1.3.0

## Release Type

- First Commercial Release
- Commercial Baseline Version

## What The Product Includes

- supported single-node self-hosted install
- signed update system
- rollback and recovery flow
- `vpnmanager` operational CLI
- backup and restore
- disaster recovery workflow
- support bundle
- operational modes
- systemd-managed services
- current operator documentation

## Supported Configuration

- Ubuntu Server 24.04 LTS and 22.04 LTS
- single-node control plane
- local PostgreSQL
- operations through `install.sh` and `vpnmanager`

## Known Issues

See:
- [known-issues.md](known-issues.md)

Current documented known issues:
- early portal warning in installer verification window
- transient portal warning after full services restart
- active-update backup block not fully reproducible via current public CLI-only surface

## Upgrade Path From 1.2.x

- `1.2.x` is the pre-release / hardening / test line
- `1.3.0` is the first commercial stable line
- operators may validate `1.3.0` through the `test` channel first, then adopt it as the production baseline

## Freeze Contract

Within `1.3.x`, the following are frozen public contracts:
- `install.sh`
- `vpnmanager` CLI command names
- CLI JSON output families
- CLI exit code semantics
- backup archive format
- restore workflow
- disaster recovery workflow
- release-layout baseline behavior
