# Contributing to Flirexa

Thanks for taking the time to contribute. This document explains how the repository is organised, what kind of changes we welcome, and the conventions we follow.

## What we accept

- **Bug fixes** — please include a reproduction case in the issue or PR.
- **Documentation improvements** — typos, clarifications, missing setup steps.
- **Translations** — we ship 6 languages today; more are welcome.
- **Community plugins** — drop a new directory under `plugins/` with a manifest. See `plugins/_example/` for the template.
- **Compatibility patches** — newer Ubuntu / Debian, alternative database setups.
- **Performance fixes** with measurable before/after numbers.
- **Security fixes** — please follow the process in `SECURITY.md`.

## What we don't accept (without prior discussion)

- Removing license gates from paid features. The gates fund development; circumventing them in the public repo defeats the open-core model. If you have a strong case for moving a specific feature into the open core, please open an issue first.
- Large architectural rewrites without a design discussion in an issue.
- New features that duplicate something a paid plugin already provides.
- Telemetry, analytics, or any phone-home behaviour in the open core. FREE installs must never make outbound calls beyond what users explicitly configure.

## Setup

```bash
git clone https://github.com/Flirexa/flirexa.git
cd flirexa
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pytest
```

## Code style

- **Python**: follow the existing style. Type hints on public APIs. No new `print()` calls in production code — use `loguru` / `logging`.
- **Vue**: composition API, `<script setup>`, no class components.
- **Commits**: imperative present tense, lowercase prefix, brief subject; details in the body.
  - Good: `fix: handle empty config in install.sh`
  - Bad: `Fixed a bug`

## Pull request checklist

- [ ] Tests pass: `pytest tests/`
- [ ] No new `from src.modules.integrity` imports (the integrity module was removed in 1.5.0).
- [ ] No personal data in commits or files (IPs, hostnames, real customer names, real email addresses). Use RFC 5737 ranges (203.0.113.x) and `example.com` for placeholders.
- [ ] Plugin changes include the corresponding test in `tests/test_*_plugin.py`.
- [ ] Frontend changes rebuild cleanly (`npm run build`).

## Reporting bugs

Open an issue with:
- What you ran (one-liner install? source? Docker?)
- OS version (`cat /etc/os-release`)
- Flirexa version (`cat VERSION`)
- The exact steps to reproduce.
- Relevant log lines from `journalctl -u vpnmanager-api` (with secrets redacted).

## Reporting security issues

**Do not open a public issue.** See `SECURITY.md`.

## Questions

For general questions, open a Discussion. For implementation questions, open an issue. For commercial enquiries (pricing, support contracts), the contact in `LICENSE` and the project homepage applies.
