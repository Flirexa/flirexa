# Versioning

## Product Version Lines

- `1.2.x` — pre-release / hardening / test line
- `1.3.0` — First Commercial Release
- `1.3.x` — first commercial maintenance line
- `1.4.x` — current active commercial line with backward-compatible additive changes
- `2.0.0` — only for breaking changes

## Line Semantics

### `1.3.0`
Meaning:
- first stable commercial release
- commercial baseline for customers and support

### `1.3.x`
Allowed:
- bugfixes
- security fixes
- small UX improvements
- supportability improvements

Not allowed:
- breaking CLI changes
- breaking backup/restore changes
- breaking update/install behavior
- breaking release-layout contract

### `1.4.x`
Meaning:
- current active commercial line
- carries forward the commercial baseline introduced in `1.3.0`

Allowed:
- new features
- additive operational capabilities
- bugfixes, security fixes, UX fixes, and supportability work
- additions that remain backward compatible

### `2.0.0`
Reserved for:
- breaking architecture changes
- breaking CLI contract changes
- breaking backup/restore format changes
- incompatible operational contract changes
