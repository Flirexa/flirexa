# Commercial Baseline

## First Commercial Release

First Commercial Release:
- `1.3.0`

Current commercial line carrying this baseline:
- `1.4.x`

`1.2.x` remains the pre-release / hardening / test line that led into the first commercial release.

## What The Baseline Includes

The baseline includes the supported operational surface of the product:
- `install.sh`
- update system
- release layout (`releases/current`)
- `vpnmanager` CLI
- backup subsystem
- restore subsystem
- disaster recovery workflow
- support bundle
- operational mode system
- maintenance mode
- systemd services
- license logic
- status/health API and local health checks
- current product documentation

## What The Baseline Guarantees

For supported single-node installations, the baseline guarantees:
- clean install on supported OS
- working local operational CLI
- deterministic service layout under systemd
- full backup creation
- restore on the same server
- disaster recovery restore onto a fresh supported server
- support bundle generation
- stable product command surface through `install.sh` and `vpnmanager`

## What The Baseline Does Not Guarantee

Not guaranteed in the commercial baseline:
- multi-node control-plane deployment
- high-availability clustering
- unsupported Linux distributions
- arbitrary manual edits to systemd units, PostgreSQL roles, or runtime files
- direct modification of product-managed state outside documented product interfaces

## Supported Configuration

Supported configuration for this baseline:
- deployment model: single-node self-hosted control plane
- supported OS:
  - Ubuntu Server 24.04 LTS
  - Ubuntu Server 22.04 LTS
- supported install mode:
  - fresh install using release archive + `install.sh`
- supported management interface:
  - `install.sh`
  - `vpnmanager`
- supported service manager:
  - `systemd`
- supported database model:
  - local PostgreSQL provisioned by installer

## Official Public Interfaces

Public product interfaces frozen for the commercial baseline:
- `install.sh`
- update system / update apply behavior
- release layout under `releases/current`
- `vpnmanager` CLI
- backup archive format
- restore behavior
- disaster recovery workflow
- support bundle structure
- status/health API used by UI
- operational mode model

## Unsupported / Manual Modification

Unsupported unless explicitly directed by support:
- editing `.env` without change control
- modifying product-managed systemd units manually
- changing PostgreSQL roles/passwords manually
- replacing files inside install root outside install/update/restore flow
- restoring backup contents manually without `vpnmanager restore`
- calling internal Python modules directly as an operational workflow
- bypassing product locks or update state by direct DB manipulation

## Freeze Rule

Within the commercial line, currently `1.4.x`, do not break:
- CLI command names
- CLI exit code semantics
- CLI JSON contracts
- backup archive format
- restore workflow
- `install.sh` behavior contract
- `update_apply.sh` behavior contract
- `releases/current` baseline layout model
