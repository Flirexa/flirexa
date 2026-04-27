# Contributing to Flirexa

Thanks for taking the time to contribute. This document explains how the repository is organised, what kind of changes we welcome, and how to set up a working development environment.

---

## What we accept

- **Bug fixes** — please include a reproduction case in the issue or PR.
- **Documentation improvements** — typos, clarifications, missing setup steps.
- **Translations** — we ship 6 languages today (`src/web/frontend/src/i18n/locales/`); more are welcome.
- **Community plugins** — drop a new directory under `plugins/` with a manifest declaring `requires_license_feature: "community"`. See `plugins/prometheus-metrics/` for the canonical example and [`docs/plugins.md`](docs/plugins.md) for the full guide.
- **Compatibility patches** — newer Ubuntu / Debian / RHEL releases, alternative database setups, container runtimes.
- **Performance fixes** with measurable before/after numbers.
- **Security fixes** — please follow the process in [`SECURITY.md`](SECURITY.md).

## What we don't accept (without prior discussion)

- **Removing license gates from paid features.** The gates fund development; circumventing them in the public repo defeats the open-core model. If you have a strong case for *moving* a specific feature into the open core, please open an issue first.
- **Large architectural rewrites** without a design discussion in an issue.
- **New features that duplicate something a paid plugin already provides.**
- **Telemetry, analytics, or any phone-home behaviour** in the open core. FREE installs must never make outbound calls beyond what the operator explicitly configures.

---

## Development environment

### The fast path

1. **Clone**:

   ```bash
   git clone https://github.com/Flirexa/flirexa.git
   cd flirexa
   ```

2. **Bring up Postgres**:

   ```bash
   docker compose -f docker-compose.dev.yml up -d
   ```

   This starts a single `postgres:16-alpine` container on `localhost:5432` with a pre-created `flirexa_dev` database (user `flirexa`, password `flirexa-dev`). Data persists in a Docker volume between restarts.

3. **Set up Python**:

   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

4. **Configure**:

   ```bash
   cp .env.example .env
   # edit .env: set DATABASE_URL, JWT_SECRET, VMS_ENCRYPTION_KEY at minimum
   ```

   For local development you can use these values:

   ```ini
   DATABASE_URL=postgresql://flirexa:flirexa-dev@localhost:5432/flirexa_dev
   JWT_SECRET=dev-jwt-secret-do-not-use-in-prod
   VMS_ENCRYPTION_KEY=dev-encryption-key-32bytes-min!!
   SERVICE_API_TOKEN=dev-service-token
   ```

5. **Run migrations**:

   ```bash
   alembic upgrade head
   ```

6. **Start the services** (each in its own terminal):

   ```bash
   python main.py                          # admin API on :10086
   python client_portal_main.py            # client portal on :10090
   python -m src.bots.admin_bot            # Telegram bot — needs ADMIN_BOT_TOKEN
   ```

7. **Run tests**:

   ```bash
   pytest tests/
   ```

   The full suite finishes in about a minute on a modest laptop. Some tests in `test_payment_flow.py` are pre-existing failures (they exercise unfinished webhook flows); the CI workflow ignores them by name.

### What's actually running

| Process | Port | Purpose |
|---|:-:|---|
| `main.py` | 10086 | Admin API + Vue 3 SPA |
| `client_portal_main.py` | 10090 | Client portal (separate FastAPI process) |
| `worker_main.py` | – | Background tasks (license heartbeat, monitoring) |
| `admin_bot.py` | – | Telegram admin bot (only with `ADMIN_BOT_TOKEN` set) |
| Postgres (container) | 5432 | Database |

You can run any subset depending on what you're working on. The admin API is the only mandatory one.

### Frontend development

The Vue 3 admin SPA and client portal source live in `src/web/frontend/` and `src/web/client-portal/`. To work on them with hot reload:

```bash
cd src/web/frontend
npm install
npm run dev          # serves on :5173 with proxy to the API on :10086

# or for the client portal
cd src/web/client-portal
npm install
npm run dev
```

Production builds (what `install.sh` deploys) are produced by `npm run build`.

### Running a specific test

```bash
# A single file
pytest tests/test_license_free_tier.py

# A single test
pytest tests/test_license_free_tier.py::TestFreeTierConfiguration::test_free_limits

# With output
pytest -s tests/test_plugin_loader.py
```

---

## Code style

- **Python**: follow the existing style. Type hints on public APIs. No new `print()` calls in production code — use `loguru` / `logging`.
- **Vue**: composition API, `<script setup>`, no class components.
- **Commits**: imperative present tense, lowercase prefix (`feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`), brief subject; details in the body.
  - Good: `fix: handle empty config in install.sh`
  - Bad: `Fixed a bug`
- **Plugin code**: see [`docs/plugins.md`](docs/plugins.md) for the do's and don'ts.

---

## Pull request checklist

- [ ] Tests pass: `pytest tests/`
- [ ] No new `from src.modules.integrity` imports — the integrity module was removed in 1.5.0; see [CHANGELOG.md](CHANGELOG.md) for why.
- [ ] No personal data in commits or files (real IPs, hostnames, customer names, real email addresses). Use RFC 5737 ranges (203.0.113.x) and `example.com` for placeholders.
- [ ] Plugin changes include the corresponding test in `tests/test_*_plugin.py`.
- [ ] Frontend changes rebuild cleanly (`npm run build`).
- [ ] If your change touches a paid feature, **both** FREE and paid behaviour are still verified by tests (typically: paid endpoint returns 403 on FREE, expected response on paid).

---

## Reporting bugs

Open an issue with:

- What you ran (one-liner install? source? Docker?)
- OS version (`cat /etc/os-release`)
- Flirexa version (`cat VERSION`)
- The exact steps to reproduce.
- Relevant log lines from `journalctl -u vpnmanager-api` (with secrets redacted).

The repo has issue templates that prompt for these — please use them.

## Reporting security issues

**Do not open a public issue.** See [`SECURITY.md`](SECURITY.md).

## Questions

For general questions, open a [Discussion](https://github.com/Flirexa/flirexa/discussions). For implementation questions, open an issue. For commercial enquiries (pricing, support contracts), email `support@flirexa.biz`.

---

## Releases

Releases follow [SemVer](https://semver.org/) with the conventional `MAJOR.MINOR.PATCH`:

- **MAJOR**: breaking changes to the public API or to the plugin interface
- **MINOR**: new features, new plugins, backward-compatible API additions
- **PATCH**: bug fixes, doc improvements, performance tweaks

The full changelog lives in [`CHANGELOG.md`](CHANGELOG.md). The active development branch is `main`; releases are tagged and visible at [github.com/Flirexa/flirexa/releases](https://github.com/Flirexa/flirexa/releases).
