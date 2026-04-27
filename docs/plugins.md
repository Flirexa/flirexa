# Plugins

How the plugin system works, how to write your own community plugin, and what makes paid plugins different.

---

## Concepts

A **plugin** is a directory under `plugins/` that:

1. Has a `manifest.json` describing itself.
2. Has an `__init__.py` that exports a `PLUGIN` symbol — an instance of `Plugin` (or a subclass).
3. Optionally provides a FastAPI router, background tasks, or DB models.

When the API starts, the **plugin loader** (`src/modules/plugin_loader/`):

1. Scans `plugins/`, skipping `_example/`, `payments/`, `__pycache__/`, and any directory whose name starts with `_`.
2. For each remaining directory, validates the `manifest.json`.
3. Checks `LicenseManager.has_feature(manifest.requires_license_feature)`.
4. If the licence grants the feature, imports `__init__.py`, instantiates `PLUGIN`, and mounts its router on the FastAPI app.
5. Calls `plugin.on_load()` for any one-time setup.

The whole thing is fail-soft: a broken plugin is logged and skipped, never crashes the API.

---

## Plugin types

There are three categories you'll see in the wild:

### 1. Community plugins (`requires_license_feature: "community"`)

Free-as-in-freedom additions written by anyone. The licence feature `community` is treated as **always granted**, so these plugins load on every install — FREE included. Use this for:

- Notification routing (Slack / Discord / Telegram alerts to operator)
- Monitoring exporters (Prometheus / Grafana metrics)
- Integration plugins (Zapier-style hooks, custom webhooks)
- UI customisations
- Locale extensions

Example: a community plugin that POSTs every new client signup to a Discord webhook.

### 2. Drop-in payment providers (`plugins/payments/`)

A separate, simpler plugin format dating back from before the generic loader existed. Each `.py` file in `plugins/payments/` defining a `PROVIDER_CLASS` is auto-registered as a payment provider. Six providers ship out of the box: NOWPayments (default), CryptoPay, Stripe, Mollie, Razorpay, Payme.

To add a new payment provider, copy `plugins/payments/_template.py`, fill in the `create_invoice` / `check_payment` methods, configure credentials in `.env`, restart.

### 3. Paid plugins (license-gated)

Distributed by the official Flirexa licence server to paying subscribers. From the loader's point of view they look identical to community plugins — same manifest format, same `Plugin` base class — they just declare a non-`community` `requires_license_feature` and only load on installs whose licence grants that feature.

For most paid plugins, the source lives in this repository (the gate is the protection). For two especially fork-sensitive ones (`extra-protocols`, `corporate-vpn`), the implementation lives in the closed `Flirexa/flirexa-pro` repo and reaches paying users through signed plugin packages.

---

## Writing a community plugin

Walkthrough: let's build `discord-alerts` — posts to a Discord webhook whenever a new client subscribes.

### Step 1: directory layout

```
plugins/discord-alerts/
├── manifest.json
└── __init__.py
```

### Step 2: manifest

```json
{
  "name": "discord-alerts",
  "version": "1.0.0",
  "display_name": "Discord Alerts",
  "description": "Posts new-client and payment events to a Discord webhook.",
  "requires_license_feature": "community",
  "author": "your-handle"
}
```

Field reference:

| Field | Required | Notes |
|---|:-:|---|
| `name` | ✅ | kebab-case, 2–40 chars, must match the directory name |
| `version` | ✅ | SemVer `MAJOR.MINOR.PATCH` |
| `display_name` | ✅ | non-empty, shown in admin UI |
| `requires_license_feature` | ✅ | `community` for free plugins; specific feature flag for licensed |
| `description` | optional | one-line summary |
| `min_app_version` | optional | minimum Flirexa version |
| `min_tier` | optional | informational: `community` / `starter` / `business` / `enterprise` |
| `author` | optional | GitHub handle or contact |
| `homepage` | optional | URL |
| `frontend_chunks` | optional | list of Vue chunk names to lazy-load on admin |

Unknown fields cause manifest validation to fail loudly — typo-resistant.

### Step 3: implementation

```python
"""Discord alerts plugin."""

import os
import httpx
from fastapi import APIRouter, Request

from src.modules.plugin_loader import Plugin

router = APIRouter(prefix="/api/v1/plugins/discord-alerts", tags=["plugins"])


@router.post("/event")
async def receive_event(request: Request):
    """Internal hook called by the subscription manager when an event fires."""
    body = await request.json()
    webhook = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook:
        return {"posted": False, "reason": "DISCORD_WEBHOOK_URL not set"}

    async with httpx.AsyncClient(timeout=5) as client:
        await client.post(webhook, json={
            "content": f":new: {body.get('event')}: {body.get('detail')}",
        })
    return {"posted": True}


class DiscordAlertsPlugin(Plugin):
    def get_router(self):
        return router

    def on_load(self):
        # Place to subscribe to internal event bus, register listeners, etc.
        # For this trivial example we just log that we're alive.
        from loguru import logger
        logger.info("discord-alerts plugin loaded")


_MANIFEST = {
    "name": "discord-alerts",
    "version": "1.0.0",
    "display_name": "Discord Alerts",
    "requires_license_feature": "community",
}

PLUGIN = DiscordAlertsPlugin(_MANIFEST)
```

### Step 4: configure

```bash
echo 'DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/xxx/yyy' >> /opt/vpnmanager/.env
sudo systemctl restart vpnmanager-api
```

### Step 5: verify

```
INFO ... Plugin loaded: Discord Alerts v1.0.0 (discord-alerts)
```

The plugin's status route is now mounted at `/api/v1/plugins/discord-alerts/event`.

---

## Plugin lifecycle hooks

The `Plugin` base class provides four hooks. Override the ones you need.

```python
class Plugin:
    def get_router(self) -> Optional[APIRouter]:
        """Return a FastAPI router to mount, or None if the plugin
        doesn't add HTTP endpoints."""
        return None

    def get_features(self) -> list[str]:
        """Return additional feature flags this plugin provides at runtime.
        Used by the admin UI to decide which feature cards to show."""
        return [self.requires_license_feature]

    def on_load(self) -> None:
        """Called once after the plugin has been successfully loaded.
        Use for: subscribing to events, priming caches, starting
        background tasks. Errors raised here are logged but don't
        prevent the plugin from being marked active."""

    def on_unload(self) -> None:
        """Called when the plugin is being unloaded (rare; happens on
        graceful shutdown or licence revocation). Use for cleanup."""
```

---

## Database migrations from a plugin

A plugin that needs its own tables ships an Alembic migration branch:

```
plugins/your-plugin/
├── manifest.json
├── __init__.py
└── alembic/
    └── versions/
        └── 001_create_your_table.py
```

In the migration, set a `branch_labels` so Alembic treats it as a separate head:

```python
revision = "yourpl_001"
down_revision = None
branch_labels = ("your_plugin",)
depends_on = "core_head"
```

The plugin loader picks up `alembic/versions/` automatically and runs `alembic upgrade your_plugin@head` on first activation. Deactivation does **not** drop the tables — your data sticks around.

---

## Frontend integration

Plugins can ship Vue components that the admin SPA lazy-loads. Add to `manifest.json`:

```json
{
  ...
  "frontend_chunks": ["DiscordAlertsSettings.vue"]
}
```

Place the file at `plugins/discord-alerts/frontend/DiscordAlertsSettings.vue`. The build pipeline picks it up automatically. The chunk loads only when the user navigates to the plugin's settings panel — no startup cost.

(Frontend integration is in active development; the manifest field is honored but the build pipeline glue is still being polished. Track progress in [ROADMAP.md](../ROADMAP.md).)

---

## Distributing your plugin

For community plugins:

1. Push to a public repo on GitHub (or wherever).
2. Open a PR adding a single line to `docs/plugins-marketplace.md` (coming soon) — name, repo URL, one-line description.
3. Operators install with `cd /opt/vpnmanager/current && git clone https://github.com/you/your-plugin plugins/your-plugin && systemctl restart vpnmanager-api`.

A more polished distribution mechanism (one-line install command from the panel) is on the roadmap.

For commercial plugins (you want to charge for them): contact `support@flirexa.biz`. We're open to a marketplace cut for third-party paid plugins; the infrastructure for it is part of the 2026 Q3 roadmap item "Plugin marketplace."

---

## What plugins should and shouldn't do

✅ **Good plugin behaviour:**
- Single, clear purpose
- Configuration via `.env` env vars, not hardcoded
- Mount routes under `/api/v1/plugins/<name>/...`
- Idempotent — safe to reload, restart, even if your data already exists
- Log via `loguru` so logs end up in the right place

❌ **Avoid:**
- Modifying core SQLAlchemy models. Add your own tables instead.
- Reaching into private symbols of `src/api/` modules. The public API is the place.
- Doing slow work in `on_load()` — that blocks API startup. Spawn a background task instead.
- Phoning home without operator consent. Even community plugins should ask `OPERATOR_ANALYTICS_ENABLED=true` first.

---

## Where the plugin system is going

Tracked in [ROADMAP.md](../ROADMAP.md):

- **2026 Q3:** signed plugin distribution from the licence server (paid plugins as `.tar.gz` packages)
- **2026 Q3:** plugin marketplace with curated community plugins
- **2026 Q3:** one-line install from the admin panel
- **2026 Q4:** frontend chunk lazy-loading polished

If you want to pre-empt the marketplace and build something now, go for it — the plugin API is stable and the manifest format won't change.
