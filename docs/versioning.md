# Versioning

_Last verified: 2026-07-24._

Flirexa uses semantic versions: `MAJOR.MINOR.PATCH`.

- `PATCH` fixes defects or security/supportability problems without intentionally
  changing documented interfaces.
- `MINOR` adds backward-compatible capability.
- `MAJOR` may change API, CLI, backup, installer, or deployment contracts and
  requires explicit migration notes.

The current source-tree version is the single line in `VERSION`:

```bash
cat VERSION
```

The current public release is available from GitHub without hard-coding a version
in this document:

```bash
git ls-remote --tags --refs https://github.com/Flirexa/flirexa.git \
  | sed 's#.*refs/tags/##' | sort -V | tail -1
```

Release notes are append-only in [CHANGELOG.md](../CHANGELOG.md). Installed
systems should normally update through the signed manifest channel described in
[updates.md](updates.md), not by checking out an arbitrary tag over a running
installation.
