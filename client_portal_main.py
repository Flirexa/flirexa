#!/usr/bin/env python3
"""
VPN Manager Client Portal - Standalone Server
Separate web server for client dashboard on port 10090.
Communicates with Admin API via internal endpoints (SERVICE_API_TOKEN).
"""

import os
import sys
from pathlib import Path

# Add project root and src/ to path (src/ needed for PyArmor runtime lookup)
_root = Path(__file__).parent
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / "src"))

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from src.database.connection import engine, Base
from src.api.routes import client_portal, corporate
from src.modules.subscription.cryptopay_adapter import CryptoPayAdapter
from src.modules.subscription.admin_api_client import AdminAPIClient

import logging
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    print("🚀 Starting VPN Manager Client Portal...")

    # Initialize database (portal tables only)
    Base.metadata.create_all(bind=engine)
    print("✅ Database initialized")

    # Initialize Admin API client
    admin_api_url = os.getenv("ADMIN_API_URL", "http://localhost:10086")
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
            from src.modules.subscription.crypto_payment import CryptoPaymentProvider
            client_portal.nowpayments_provider = CryptoPaymentProvider(
                api_key=np_key, ipn_secret=np_secret, sandbox=np_sandbox
            )
            print(f"✅ NOWPayments initialized (sandbox: {np_sandbox})")
        except Exception as e:
            logger.warning(f"NOWPayments init error: {e}")
            print(f"⚠️  NOWPayments not available: {e}")
    else:
        print("ℹ️  NOWPayments not configured (set NOWPAYMENTS_API_KEY)")

    yield

    # Shutdown
    print("👋 Shutting down VPN Manager Client Portal...")


# Create FastAPI app
app = FastAPI(
    title="VPN Manager Client Portal",
    description="VPN Client Dashboard & Subscription Management",
    version="2.0.0",
    lifespan=lifespan
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
        "version": "2.0.0"
    }

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
            return FileResponse(str(apk_path), filename="VPN Manager.apk", media_type="application/vnd.android.package-archive")
        return JSONResponse({"detail": "APK not found"}, status_code=404)

    # Serve static files
    if full_path.startswith("assets/"):
        return JSONResponse({"detail": "Not Found"}, status_code=404)

    # Try to serve static file directly (icons, manifest, sw.js)
    static_file = STATIC_DIR / full_path
    if static_file.is_file():
        return FileResponse(static_file)

    # Serve index.html for all other routes (SPA)
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
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
║         VPN Manager Client Portal v2.0                      ║
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
