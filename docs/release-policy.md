# Release Policy

## Release Lines

- `1.2.x` — pre-release / hardening / test line
- `1.3.x` — first commercial maintenance line
- `1.4.x` — current active commercial line
- `2.0.0` — breaking-change line only

## First Commercial Release

First Commercial Release:
- `1.3.0`

Current active commercial line after that:
- `1.4.x`

## Policy For `1.3.x`

Allowed changes:
- real bugfixes
- security fixes
- small UX improvements
- supportability/documentation updates

Not allowed casually:
- breaking CLI changes
- breaking backup format changes
- breaking restore workflow changes
- breaking update/install behavior changes
- breaking release-layout changes

## Policy For `1.4.x`

Allowed:
- new features
- additive product capabilities
- bugfixes and security fixes
- supportability and UX improvements
- new flows that do not break existing supported behavior

## Breaking Change Policy

If a change breaks:
- CLI contracts
- backup archive format
- restore semantics
- install/update baseline behavior
- releases/current operational model

then it is not a `1.3.x` or `1.4.x` maintenance change and must be treated as at least `2.0.0` territory.

## Documentation Rule

A release is not commercially acceptable if:
- supported operational behavior changed
- but public docs were not updated

## Support Rule

Each commercial release must be supportable through:
- `install.sh`
- `vpnmanager status`
- `vpnmanager health`
- `vpnmanager support-bundle`
- `vpnmanager backup`
- `vpnmanager restore`
- documented disaster recovery runbook
