#!/usr/bin/env python3
"""
Flirexa client portal - standalone server
Separate web server for client dashboard on port 10090.
Communicates with Admin API via internal endpoints (SERVICE_API_TOKEN).
"""

import os
import sys
from pathlib import Path

# Add project root and src/ to the package search path.
_root = Path(__file__).parent
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / "src"))

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from src.database.connection import engine, Base
from src.api.routes import client_portal, corporate
from src.modules.subscription.cryptopay_adapter import CryptoPayAdapter
from src.modules.subscription.admin_api_client import AdminAPIClient
from src.utils.runtime_paths import get_app_version

import logging
logger = logging.getLogger(__name__)
APP_VERSION = get_app_version()


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    print("🚀 Starting Flirexa Client Portal...")

    # Initialize database (portal tables only)
    Base.metadata.create_all(bind=engine)
    print("✅ Database initialized")

    # Initialize Admin API client.
    #
    # ADMIN_API_URL is the INTERNAL URL the portal uses to talk to the
    # admin process — it should point at the admin's plain-HTTP port,
    # never at the nginx HTTPS port. When `configure-web-access.sh` puts
    # nginx with a Let's Encrypt cert on 10086 (admin-domain mode), it
    # bumps the admin python service to API_PORT=10087 and leaves 10086
    # HTTPS-only. If ADMIN_API_URL stays at the legacy default
    # `http://localhost:10086`, the portal hits nginx with a plain-HTTP
    # request and gets `400 The plain HTTP request was sent to HTTPS port`
    # — every device list / device add / device delete silently fails,
    # the portal shows zero devices, and the customer can't manage what
    # the admin already issued. So we derive the default from API_PORT
    # instead of hardcoding the old port; an explicit ADMIN_API_URL in
    # .env still wins.
    api_port = os.getenv("API_PORT", "10086")
    admin_api_url = os.getenv("ADMIN_API_URL", f"http://localhost:{api_port}")
    service_token = os.getenv("SERVICE_API_TOKEN", "")
    if service_token:
        client_portal.admin_api = AdminAPIClient(
            base_url=admin_api_url,
            service_token=service_token,
        )
        print(f"✅ Admin API client initialized ({admin_api_url})")
    else:
        print("⚠️  SERVICE_API_TOKEN not set — WireGuard operations will fail")

    # Initialize CryptoPay adapter
    cryptopay_token = os.getenv("CRYPTOPAY_API_TOKEN")
    cryptopay_testnet = os.getenv("CRYPTOPAY_TESTNET", "false").lower() == "true"

    if cryptopay_token:
        client_portal.cryptopay_adapter = CryptoPayAdapter(
            api_token=cryptopay_token,
            testnet=cryptopay_testnet
        )
        print(f"✅ CryptoPay initialized (testnet: {cryptopay_testnet})")
    else:
        print("⚠️  CryptoPay not configured (set CRYPTOPAY_API_TOKEN)")

    # Initialize PayPal provider
    pp_id = os.getenv("PAYPAL_CLIENT_ID", "")
    pp_secret = os.getenv("PAYPAL_CLIENT_SECRET", "")
    pp_sandbox = os.getenv("PAYPAL_SANDBOX", "true").lower() == "true"
    pp_webhook_id = os.getenv("PAYPAL_WEBHOOK_ID", "")
    if pp_id and pp_secret:
        try:
            from src.modules.payment.providers.paypal import PayPalProvider
            provider = PayPalProvider(
                client_id=pp_id, client_secret=pp_secret,
                sandbox=pp_sandbox, webhook_id=pp_webhook_id
            )
            test = await provider.test_connection()
            if test["connected"]:
                client_portal.paypal_provider = provider
                print(f"✅ PayPal initialized (sandbox: {pp_sandbox})")
            else:
                print(f"⚠️  PayPal connection failed: {test['message']}")
        except Exception as e:
            logger.warning(f"PayPal init error: {e}")
            print(f"⚠️  PayPal not available: {e}")
    else:
        print("ℹ️  PayPal not configured (set PAYPAL_CLIENT_ID + PAYPAL_CLIENT_SECRET)")

    # Initialize NOWPayments provider
    np_key = os.getenv("NOWPAYMENTS_API_KEY", "")
    np_secret = os.getenv("NOWPAYMENTS_IPN_SECRET", "")
    np_sandbox = os.getenv("NOWPAYMENTS_SANDBOX", "false").lower() == "true"
    if np_key:
        try:
            # Use the hosted-checkout NOWPaymentsProvider (POST /v1/invoice +
            # `ipn_callback_url`), matching what `src/api/main.py` loads. The
            # legacy `CryptoPaymentProvider` posts to /v1/payment, which
            # rejects every request from the create-invoice flow because the
            # metadata key it reads (`callback_url`) is never set — every
            # customer hits "API error: ipn_callback_url must be a string".
            from src.modules.payment.providers.nowpayments import NOWPaymentsProvider
            client_portal.nowpayments_provider = NOWPaymentsProvider(
                api_key=np_key, ipn_secret=np_secret, sandbox=np_sandbox
            )
            print(f"✅ NOWPayments initialized (sandbox: {np_sandbox})")
        except Exception as e:
            logger.warning(f"NOWPayments init error: {e}")
            print(f"⚠️  NOWPayments not available: {e}")
    else:
        print("ℹ️  NOWPayments not configured (set NOWPAYMENTS_API_KEY)")

    # Load payment plugins from plugins/payments/ (Stripe, Mollie, Payme,
    # Razorpay). Mirrors the admin lifespan in src/api/main.py — the portal
    # process serves /client-portal/payments/providers AND /payments/invoice,
    # so without this block customers see only CryptoPay/PayPal/NOWPayments
    # in the picker even when admin Settings shows Stripe as Active. The
    # admin process loading plugins doesn't help here: it's a separate
    # PID with its own client_portal module instance.
    #
    # Use package imports for both source plugins in development and compiled
    # `.abi3.so` providers in official customer archives.
    try:
        import importlib
        from pathlib import Path as _P
        from src.modules.payment.plugin_discovery import importable_payment_modules
        _plugins_dir = _P(__file__).resolve().parent / "plugins" / "payments"
        if _plugins_dir.is_dir():
            _loaded = 0
            for _module_name, _pf in importable_payment_modules(_plugins_dir):
                try:
                    _mod = importlib.import_module(f"plugins.payments.{_module_name}")
                    _cls = getattr(_mod, "PROVIDER_CLASS", None)
                    if _cls:
                        _instance = _cls()
                        setattr(client_portal, f"{_instance.name}_provider", _instance)
                        print(f"✅ Payment plugin loaded: {_instance.display_name} ({_pf.name})")
                        _loaded += 1
                except Exception as _pe:
                    logger.warning(f"Payment plugin {_pf.name} failed to load: {_pe}")
                    print(f"⚠️  Payment plugin {_pf.name} skipped: {_pe}")
            if _loaded:
                print(f"✅ Loaded {_loaded} payment plugin(s)")
    except Exception as _pe:
        logger.debug(f"Plugin loader: {_pe}")

    yield

    # Shutdown
    print("👋 Shutting down Flirexa Client Portal...")


# Create FastAPI app
_api_docs_enabled = _env_flag("CLIENT_PORTAL_API_DOCS_ENABLED", False)
app = FastAPI(
    title="Flirexa Client Portal",
    description="VPN Client Dashboard & Subscription Management",
    version=APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs" if _api_docs_enabled else None,
    redoc_url="/redoc" if _api_docs_enabled else None,
    openapi_url="/openapi.json" if _api_docs_enabled else None,
)

# CORS middleware
cors_origins = os.getenv("CORS_ORIGINS", "").strip()
_allowed_origins = [o.strip() for o in cors_origins.split(",") if o.strip()] if cors_origins else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True if cors_origins else False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# License enforcement: check client_portal feature
@app.middleware("http")
async def license_middleware(request, call_next):
    """Block client portal if license doesn't include client_portal feature"""
    from fastapi.responses import JSONResponse as _JSONResponse
    path = request.url.path
    # Always allow: branding, health, static
    if path.startswith("/api/v1/public/") or path.startswith("/assets/") or path == "/" or not path.startswith("/api/"):
        return await call_next(request)
    license_enabled = os.getenv("LICENSE_CHECK_ENABLED", "false").lower() == "true"
    if license_enabled:
        try:
            from src.modules.license.manager import get_license_manager
            mgr = get_license_manager()
            info = mgr.get_license_info()
            if info.is_expired() and not info.in_grace_period():
                return _JSONResponse(status_code=403, content={"detail": "License expired."})
            if not info.has_feature("client_portal"):
                return _JSONResponse(status_code=403, content={"detail": "Client portal requires Business or Enterprise license."})
        except Exception:
            pass
    return await call_next(request)

# IMPORTANT: All API routers must be registered BEFORE the catch-all
# GET /{full_path:path} route below, otherwise API POST/PUT/DELETE
# requests will be shadowed by the catch-all and return 405.
app.include_router(client_portal.router, tags=["Client Portal"])

# Corporate VPN — client portal routes (portal JWT auth)
app.include_router(
    corporate.portal_router,
    prefix="/client-portal/corporate",
    tags=["Corporate VPN"],
)

# Static files path — separate client portal build
STATIC_DIR = Path(__file__).parent / "src" / "web" / "client-portal-dist"

# Mount static files
if STATIC_DIR.exists():
    assets_dir = STATIC_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")
    print(f"✅ Static files mounted from {STATIC_DIR}")
else:
    print(f"⚠️  Static directory not found: {STATIC_DIR}")

# Persistent uploads directory — lives outside the release tree at
# /opt/vpnmanager/data/uploads/, so branded logos / favicons survive
# release swaps. The admin upload endpoint (POST /system/branding/logo)
# writes here too. Mounted on this portal so customers can fetch their
# operator's logo from the same origin they're already on (no admin-port
# cross-origin hop, no broken-image icon).
_install_dir = Path(os.getenv("INSTALL_DIR", "/opt/vpnmanager"))
_uploads_dir = _install_dir / "data" / "uploads"
try:
    _uploads_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=_uploads_dir), name="uploads")
    print(f"✅ Uploads mounted from {_uploads_dir}")
except Exception as _up_err:
    print(f"⚠️  Could not mount uploads dir: {_up_err}")

# No-cache headers for SPA index.html
no_cache_headers = {
    "Cache-Control": "no-cache, no-store, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0",
}

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "ok",
        "service": "vpnmanager-client-portal",
        "version": APP_VERSION
    }


# Public branding endpoint — mirrors the admin API one so the client
# portal frontend can fetch its branding without crossing origins.
# Previously the App.vue hit the admin host:port directly when running
# on 10090, but when nginx fronts the portal on 443 the customer's
# browser sees `baseUrl=""` and hits this host — and the admin endpoint
# isn't proxied through. The catch-all SPA route below would then
# return index.html (200) for `/api/v1/public/branding`, the frontend
# would parse the HTML as JSON, fail silently, and fall back to the
# bundled "Flirexa" logo and the neutral "VPN" string.
@app.get("/api/v1/public/branding")
async def public_branding():
    """Return non-sensitive branding fields for the client portal."""
    try:
        from src.modules.branding import get_all_branding
        from src.database.connection import SessionLocal
        db = SessionLocal()
        try:
            return get_all_branding(db)
        finally:
            db.close()
    except Exception as exc:
        from loguru import logger as _log
        _log.warning("public_branding read failed: {}", exc)
        return JSONResponse({}, status_code=200)


# The public portal must not advertise its entire route surface in production.
# Explicit 404 handlers keep the SPA catch-all below from returning index.html
# with a misleading 200 for the well-known documentation paths.
if not _api_docs_enabled:
    @app.get("/docs", include_in_schema=False)
    @app.get("/redoc", include_in_schema=False)
    @app.get("/openapi.json", include_in_schema=False)
    async def api_documentation_disabled():
        return JSONResponse({"detail": "Not Found"}, status_code=404)


# IMPORTANT: Catch-all route must remain LAST,
# otherwise it will shadow API routes registered above.
@app.get("/{full_path:path}")
async def serve_frontend(request: Request, full_path: str):
    """Serve Vue.js frontend for all routes"""
    # API routes are handled by routers above
    if full_path.startswith("client-portal/") or full_path.startswith("health"):
        return JSONResponse({"detail": "Not Found"}, status_code=404)

    # APK version info
    if full_path == "download/app/version":
        version_path = Path(__file__).parent / "src" / "web" / "static" / "apk-version.json"
        if version_path.is_file():
            import json
            data = json.loads(version_path.read_text())
            return JSONResponse(data)
        return JSONResponse({"version": "unknown", "version_code": 0})

    # APK download
    if full_path == "download/app":
        static_dir = Path(__file__).parent / "src" / "web" / "static"
        # Try versioned APK first, then fallback
        import glob as _glob
        versioned = sorted(_glob.glob(str(static_dir / "*-v*.apk")) + _glob.glob(str(static_dir / "*_v*.apk")), reverse=True)
        if versioned:
            apk_path = Path(versioned[0])
            return FileResponse(str(apk_path), filename=apk_path.name, media_type="application/vnd.android.package-archive")
        apk_path = static_dir / "vpn-manager.apk"
        if apk_path.is_file():
            return FileResponse(str(apk_path), filename="Flirexa.apk", media_type="application/vnd.android.package-archive")
        return JSONResponse({"detail": "APK not found"}, status_code=404)

    # Serve static files
    if full_path.startswith("assets/"):
        return JSONResponse({"detail": "Not Found"}, status_code=404)

    # manifest.json — render dynamically with customer-facing brand name
    # so PWA install + iOS "Add to Home Screen" show the operator's brand,
    # not the platform default. Static manifest is still on disk as a
    # template; we just rewrite name/short_name fields at serve time.
    if full_path == "manifest.json":
        manifest_file = STATIC_DIR / "manifest.json"
        if manifest_file.is_file():
            try:
                import json as _json
                from src.modules.branding import get_all_branding
                from src.database.connection import SessionLocal
                data = _json.loads(manifest_file.read_text(encoding="utf-8"))
                db = SessionLocal()
                try:
                    brand = get_all_branding(db)
                finally:
                    db.close()
                customer_name = (
                    (brand.get("branding_customer_app_name") or "").strip()
                    or (brand.get("branding_app_name") or "").strip()
                    or "VPN"
                )
                data["name"] = customer_name
                data["short_name"] = customer_name
                return JSONResponse(data)
            except Exception:
                # Fall through to the static file on any error
                pass

    # Try to serve static file directly (icons, manifest, sw.js)
    static_file = STATIC_DIR / full_path
    if static_file.is_file():
        return FileResponse(static_file)

    # Serve index.html for all other routes (SPA). Inject the operator's
    # customer-facing brand name into <title> and the apple-mobile-web-app
    # meta so the tab label, PWA short name, and social-share preview
    # don't show the platform default "Flirexa" — customers
    # should only ever see the operator's brand.
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        try:
            from src.modules.branding import get_all_branding
            from src.database.connection import SessionLocal
            html = index_file.read_text(encoding="utf-8")
            db = SessionLocal()
            try:
                brand = get_all_branding(db)
            finally:
                db.close()
            # Only use the operator's customer-facing name. Don't fall
            # back to ``branding_app_name`` (admin-side) here — that
            # leaks the operator's internal name into the customer's
            # browser tab when they intentionally left it empty (e.g.
            # because their logo image already contains the brand).
            # "VPN" is the last-resort neutral default so the tab is
            # never literally empty.
            customer_name = (
                (brand.get("branding_customer_app_name") or "").strip()
                or "VPN"
            )
            # Escape angle brackets defensively — operator-supplied string
            # going into raw HTML attribute / text content.
            safe = (
                customer_name
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
            )
            html = html.replace(
                "<title>Flirexa</title>",
                f"<title>{safe}</title>",
            )
            html = html.replace(
                'content="Flirexa"',
                f'content="{safe}"',
            )
            return HTMLResponse(html, headers=no_cache_headers)
        except Exception as _br_err:
            # Branding lookup failed (e.g. DB blip during cold start) —
            # falling back to the unbranded file is still better than 500.
            from loguru import logger as _log
            _log.warning("brand injection failed for index.html: {}", _br_err)
            return FileResponse(index_file, headers=no_cache_headers)
    else:
        return JSONResponse(
            {"detail": "Frontend not built. Run: cd src/web/client-portal && npm run build"},
            status_code=503
        )


def run_server():
    """Run the client portal server"""
    import uvicorn

    host = os.getenv("CLIENT_PORTAL_HOST", "0.0.0.0")
    port = int(os.getenv("CLIENT_PORTAL_PORT", "10090"))

    print(f"""
╔═══════════════════════════════════════════════════════════╗
║         Flirexa Client Portal v{APP_VERSION:<27}║
║         http://{host}:{port}                              ║
╚═══════════════════════════════════════════════════════════╝
""")

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
        access_log=True
    )


if __name__ == "__main__":
    run_server()
