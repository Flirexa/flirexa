"""
VPN Management Studio FastAPI Application
Main API entry point
"""

import os
import asyncio
from pathlib import Path
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
import sys

import time
import uuid
import psutil

from sqlalchemy.orm import Session
from ..database.connection import init_db, close_db, SessionLocal, get_db
from .routes import clients, servers, bots, payments, system, agent, client_portal, tariffs, traffic_rules, internal, admin_auth, portal_users, promo_codes, app_accounts, backup, corporate, health, updates, plugins_admin
# Register corporate models so Base.metadata.create_all() includes their tables
from ..modules.corporate import models as _corporate_models  # noqa: F401
from .middleware.auth import get_current_admin
from ..modules.subscription.cryptopay_adapter import CryptoPayAdapter
from ..modules.operational_mode import (
    is_request_allowed,
    resolve_operational_mode_from_db,
)

# Background monitoring task handle
_monitor_task: Optional[asyncio.Task] = None
_backup_task: Optional[asyncio.Task] = None
_license_validator_task: Optional[asyncio.Task] = None
_heartbeat_task: Optional[asyncio.Task] = None
_start_time: Optional[float] = None

MONITOR_INTERVAL = int(os.getenv("MONITOR_INTERVAL", "60"))

# Set up JSON file logging before any loggers are used
from ..modules.log_config import setup_logging as _setup_logging
_setup_logging("api")

# Background tasks are managed in scheduler.py — imported here for backward compat
from .scheduler import monitoring_cycle as _monitoring_cycle, monitoring_loop as _monitoring_loop
from .scheduler import backup_cycle as _backup_cycle, backup_loop as _backup_loop
from .scheduler import start_background_tasks as _start_bg_tasks


def _should_run_in_process_background_tasks() -> tuple[bool, str]:
    """
    Decide whether scheduler loops should run inside the API process.

    WORKER_ENABLED=true still wins and disables in-process scheduler entirely.
    SCHEDULER_IN_API=false allows a future standalone scheduler service without
    changing current deployments.
    """
    if os.getenv("WORKER_ENABLED", "false").lower() == "true":
        return False, "External worker detected (WORKER_ENABLED=true)"
    if os.getenv("SCHEDULER_IN_API", "true").lower() != "true":
        return False, "In-process scheduler disabled (SCHEDULER_IN_API=false)"
    return True, "Starting in-process background tasks"



@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    global _monitor_task, _license_validator_task, _heartbeat_task, _start_time

    # Startup
    _start_time = time.time()
    logger.info("EVENT:API_START VPN Manager API starting")

    # Initialize database
    init_db()
    logger.info("Database initialized")

    # Mark any update records that were interrupted by a previous restart as FAILED.
    # Must run after init_db() so the table exists.
    try:
        from ..modules.updates.manager import cleanup_orphaned_updates
        n = cleanup_orphaned_updates()
        if n:
            logger.warning("Cleaned up %d orphaned update record(s) on startup", n)
    except Exception as _e:
        logger.warning("Could not cleanup orphaned updates on startup: %s", _e)

    # Mark any bootstrap tasks that were still running as interrupted.
    try:
        from ..modules.bootstrap_logger import mark_interrupted_tasks
        mark_interrupted_tasks()
    except Exception as _e:
        logger.warning("Could not mark interrupted bootstrap tasks on startup: %s", _e)

    # Clear restart_pending flag — services have just restarted, new code is running.
    try:
        import os as _os
        from pathlib import Path as _Path
        _restart_flag = _Path(_os.getenv("INSTALL_DIR", str(_Path(__file__).resolve().parents[2]))) / "data" / "restart_pending"  # src/api/main.py → project root
        if _restart_flag.exists():
            _restart_flag.unlink()
            logger.info("Cleared restart_pending flag — services restarted successfully")
    except Exception:
        pass

    # Initialize CryptoPay adapter
    cryptopay_token = os.getenv("CRYPTOPAY_API_TOKEN")
    cryptopay_testnet = os.getenv("CRYPTOPAY_TESTNET", "false").lower() == "true"
    if cryptopay_token:
        client_portal.cryptopay_adapter = CryptoPayAdapter(
            api_token=cryptopay_token,
            testnet=cryptopay_testnet
        )
        logger.info("CryptoPay initialized")
    else:
        logger.warning("CRYPTOPAY_API_TOKEN not set - crypto payments disabled")

    # Initialize PayPal provider
    pp_id = os.getenv("PAYPAL_CLIENT_ID", "")
    pp_secret = os.getenv("PAYPAL_CLIENT_SECRET", "")
    if pp_id and pp_secret:
        try:
            from ..modules.payment.providers.paypal import PayPalProvider
            pp_sandbox = os.getenv("PAYPAL_SANDBOX", "true").lower() == "true"
            pp_webhook_id = os.getenv("PAYPAL_WEBHOOK_ID", "")
            provider = PayPalProvider(client_id=pp_id, client_secret=pp_secret, sandbox=pp_sandbox, webhook_id=pp_webhook_id)
            client_portal.paypal_provider = provider
            logger.info("PayPal initialized (sandbox=%s)", pp_sandbox)
        except Exception as e:
            logger.warning("PayPal init failed: %s", e)

    # Initialize NOWPayments provider
    np_key = os.getenv("NOWPAYMENTS_API_KEY", "")
    if np_key:
        try:
            from ..modules.payment.providers.nowpayments import NOWPaymentsProvider
            np_secret = os.getenv("NOWPAYMENTS_IPN_SECRET", "")
            np_sandbox = os.getenv("NOWPAYMENTS_SANDBOX", "false").lower() == "true"
            client_portal.nowpayments_provider = NOWPaymentsProvider(api_key=np_key, ipn_secret=np_secret, sandbox=np_sandbox)
            logger.info("NOWPayments initialized")
        except Exception as e:
            logger.warning("NOWPayments init failed: %s", e)

    # Load payment plugins from plugins/payments/
    try:
        import importlib.util
        from pathlib import Path as _P
        _plugins_dir = _P(__file__).resolve().parents[2] / "plugins" / "payments"
        if _plugins_dir.is_dir():
            _loaded = 0
            for _pf in sorted(_plugins_dir.glob("*.py")):
                if _pf.name.startswith("_"):
                    continue  # skip __init__.py and _template.py
                try:
                    _spec = importlib.util.spec_from_file_location(f"plugin_{_pf.stem}", str(_pf))
                    _mod = importlib.util.module_from_spec(_spec)
                    _spec.loader.exec_module(_mod)
                    _cls = getattr(_mod, "PROVIDER_CLASS", None)
                    if _cls:
                        _instance = _cls()
                        # Register as payment provider in client portal
                        setattr(client_portal, f"{_instance.name}_provider", _instance)
                        logger.info(f"Payment plugin loaded: {_instance.display_name} ({_pf.name})")
                        _loaded += 1
                except Exception as _pe:
                    logger.warning(f"Payment plugin {_pf.name} failed to load: {_pe}")
            if _loaded:
                logger.info(f"Loaded {_loaded} payment plugin(s)")
    except Exception as _pe:
        logger.debug(f"Plugin loader: {_pe}")

    # NOTE: generic plugin loader runs in create_app() before the SPA catch-all
    # is registered, not here. If we mounted plugin routers during lifespan,
    # the catch-all GET /{full_path:path} would already be ahead of them in
    # app.routes and would 404 every plugin URL.

    # Prime psutil CPU counter (first call always returns 0.0)
    psutil.cpu_percent()

    # Restore fail-safe state from DB (persists across restarts)
    try:
        from ..modules.failsafe import FailSafeManager
        _fs_db = SessionLocal()
        try:
            FailSafeManager.instance().load_persisted_state(_fs_db)
        finally:
            _fs_db.close()
    except Exception as _fse:
        logger.warning("Could not restore fail-safe state: %s", _fse)

    # Restore bandwidth limits (tc rules live in RAM, lost on reboot)
    try:
        from ..core.traffic_manager import TrafficManager
        db = SessionLocal()
        try:
            tm = TrafficManager(db)
            restored = tm.restore_all_bandwidth_limits()
            if restored > 0:
                logger.info(f"Restored {restored} bandwidth limits on startup")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Failed to restore bandwidth limits: {e}")

    # Start online license validator (always — independent of worker mode)
    # Use server_config.get_server_urls() — URLs may come from signed file, not env vars
    try:
        from ..modules.license.server_config import get_server_urls as _get_license_urls
        _lic_primary, _lic_backup = _get_license_urls()
    except Exception:
        _lic_primary, _lic_backup = os.getenv("LICENSE_SERVER_URL", ""), ""
    if _lic_primary or _lic_backup:
        from ..modules.license.online_validator import run_single_check, run_validator_loop
        try:
            await asyncio.wait_for(run_single_check(warm_cache=True), timeout=5)
            logger.info("Initial online license check completed during startup")
        except asyncio.TimeoutError:
            logger.warning("Initial online license check timed out after 5s — continuing startup")
        except Exception as e:
            logger.warning("Initial online license check failed during startup: %s", e)
        _license_validator_task = asyncio.create_task(run_validator_loop())
        logger.info("Online license validator started")

    # Start instance heartbeat (always — sends status even without a license)
    try:
        from ..modules.license.instance_manager import start_heartbeat_task
        _heartbeat_task = start_heartbeat_task()
    except Exception as e:
        logger.warning("Could not start instance heartbeat: %s", e)

    # Start background monitoring (skip if external worker is handling it)
    _bg_tasks = []
    run_in_process, scheduler_reason = _should_run_in_process_background_tasks()
    if not run_in_process:
        logger.info(f"{scheduler_reason} — skipping in-process background tasks")
    else:
        logger.info(scheduler_reason)
        _bg_tasks = _start_bg_tasks()
        _monitor_task = _bg_tasks[0] if _bg_tasks else None
        _backup_task  = _bg_tasks[1] if len(_bg_tasks) > 1 else None

    yield

    # Shutdown
    logger.info("EVENT:API_STOP VPN Manager API shutting down")
    for task in [_monitor_task, _backup_task, _license_validator_task, _heartbeat_task]:
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    close_db()


def create_app(
    title: str = "VPN Manager API",
    version: str = "5.0.0",
    debug: bool = False,
) -> FastAPI:
    """
    Create and configure the FastAPI application

    Args:
        title: API title
        version: API version
        debug: Enable debug mode

    Returns:
        Configured FastAPI application
    """
    app = FastAPI(
        title=title,
        description="WireGuard VPN Management API",
        version=version,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    app.state.operational_mode_session_factory = SessionLocal

    # Configure CORS
    cors_origins = os.getenv("CORS_ORIGINS", "").strip()
    allowed_origins = [o.strip() for o in cors_origins.split(",") if o.strip()] if cors_origins else ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True if cors_origins else False,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept"],
    )

    # Request ID + access log middleware (replaces bare request_id_middleware)
    from .middleware.request_logger import RequestLoggerMiddleware
    app.add_middleware(RequestLoggerMiddleware)

    # Security headers middleware
    @app.middleware("http")
    async def security_headers_middleware(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    # License enforcement middleware
    @app.middleware("http")
    async def license_middleware(request: Request, call_next):
        """Check license validity — block all requests if expired (except license endpoint)"""
        import posixpath
        from urllib.parse import unquote

        path = request.url.path
        # Double-decode + normalize the path to block bypass attempts:
        # 1. unquote() handles any remaining %XX sequences (e.g. %2F from double-encoded /../)
        # 2. posixpath.normpath() collapses ./ and ../ traversals
        # Without this, /api/v1/system/license%2F../clients would pass the whitelist.
        normalized_path = posixpath.normpath(unquote(path))

        # Always allow: license activation, health, auth, public endpoints, static files
        allowed_prefixes = (
            "/api/v1/system/license",
            "/api/v1/system/activation",
            "/api/v1/system/restart",    # restart must work even when license expired
            "/api/v1/updates",           # updates/restart must work to fix expired license
            "/api/v1/public/",
            "/api/v1/auth/",
            "/health",
            "/api/docs",
            "/api/redoc",
            "/api/openapi.json",
            "/assets/",
            "/login",
            "/activation",
            # Client portal: allow auth/login endpoints so users can always log in
            "/client-portal/auth/",
            "/client-portal/public/",
        )
        # Pass requests that match whitelist OR non-API paths except client-portal
        is_api_path = normalized_path.startswith("/api/") or normalized_path.startswith("/client-portal/")
        if any(normalized_path.startswith(p) for p in allowed_prefixes) or normalized_path == "/" or not is_api_path:
            return await call_next(request)

        # Skip license checks when explicitly disabled (tests / dev without a key)
        if os.getenv("LICENSE_CHECK_ENABLED", "true").lower() == "false":
            return await call_next(request)

        try:
            from ..modules.license.manager import get_license_manager, _find_public_key, LicenseType

            # Dev environment: no license_public.pem + INTERNAL_LICENSE_MODE → pass through
            if not _find_public_key():
                if os.getenv("INTERNAL_LICENSE_MODE", "false").lower() == "true":
                    return await call_next(request)

            mgr = get_license_manager()

            info = mgr.get_license_info()

            # ── Activation check ─────────────────────────────────────────────
            # No key or invalid/wrong-machine key → activation required
            # Trial with is_valid=True is allowed through (demo mode)
            if not mgr.is_properly_activated() and not (info.is_valid and info.type == LicenseType.TRIAL):
                hw_id = mgr.get_server_id()
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": info.validation_message or "Product not activated.",
                        "activation_required": True,
                        "activation_code": hw_id,
                    }
                )

            # ── Expiry check ─────────────────────────────────────────────────
            if info.is_expired() and not info.in_grace_period():
                hw_id = mgr.get_server_id()
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": "License expired. Please obtain a new license key.",
                        "activation_required": True,
                        "activation_code": hw_id,
                    }
                )

            # ── Online validation check ───────────────────────────────────────
            try:
                from ..modules.license.online_validator import is_license_blocked
                blocked, block_reason = is_license_blocked()
                if blocked:
                    logger.warning(f"EVENT:LICENSE_BLOCKED reason={block_reason}")
                    return JSONResponse(
                        status_code=403,
                        content={
                            "detail": f"License blocked: {block_reason}",
                            "license_blocked": True,
                        }
                    )
            except ImportError:
                pass  # online_validator not available — skip

            # ── Feature-level gating ──────────────────────────────────────────
            # Coarse URL-prefix gates for whole-router features. Per-endpoint
            # gating (where some routes are FREE and others paid in the same
            # router) lives on the routes themselves via require_license_feature.
            feature_routes = {
                "/api/v1/traffic-rules": "traffic_rules",
                "/api/v1/payments": "payments",
                "/api/v1/promo-codes": "promo_codes",
            }
            for route_prefix, feature_name in feature_routes.items():
                if normalized_path.startswith(route_prefix) and not info.has_feature(feature_name):
                    return JSONResponse(
                        status_code=403,
                        content={
                            "detail": f"Feature '{feature_name}' requires a higher license tier.",
                            "license_feature_required": feature_name,
                        }
                    )

        except Exception as e:
            logger.error(f"License check raised exception: {e}")
            return JSONResponse(
                status_code=503,
                content={
                    "detail": "License verification failed. Please contact support.",
                    "license_check_failed": True,
                }
            )

        return await call_next(request)

    @app.middleware("http")
    async def operational_mode_middleware(request: Request, call_next):
        path = request.url.path
        method = request.method.upper()

        if not path.startswith("/api/"):
            return await call_next(request)

        try:
            session_factory = getattr(app.state, "operational_mode_session_factory", SessionLocal)
            db = session_factory()
            try:
                resolved = resolve_operational_mode_from_db(db, degraded=False)
            finally:
                db.close()
        except Exception:
            return await call_next(request)

        request.state.operational_mode = resolved.mode
        request.state.maintenance_reason = resolved.maintenance_reason

        allowed, block_reason = is_request_allowed(resolved.mode, path, method)
        if not allowed:
            return JSONResponse(
                status_code=423,
                content={
                    "detail": block_reason or f"Operation blocked in mode '{resolved.mode}'",
                    "operational_mode": resolved.mode,
                    "maintenance_reason": resolved.maintenance_reason,
                },
            )

        return await call_next(request)

    # Exception handlers
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        import traceback
        tb = traceback.format_exc()
        logger.opt(exception=True).error(
            f"Unhandled exception on {request.method} {request.url.path}: {exc}"
        )
        # Also write a plain error line for easy grep
        logger.error(f"CRASH path={request.url.path} error={type(exc).__name__}: {exc}")
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "error": str(exc) if debug else None}
        )

    # Health check
    @app.get("/health", tags=["System"])
    async def health_check(detail: bool = False):
        """Health check endpoint. Use ?detail=true for component status."""
        result = {"status": "healthy", "version": version}

        if detail:
            # Database check
            try:
                from ..database.connection import check_db_connection
                result["database"] = "ok" if check_db_connection() else "error"
            except Exception:
                result["database"] = "error"

            # Worker mode
            worker_enabled = os.getenv("WORKER_ENABLED", "false").lower() == "true"
            result["background_tasks"] = "external_worker" if worker_enabled else "in_process"

            # Uptime
            result["uptime_seconds"] = int(time.time() - _start_time) if _start_time else 0

            # Memory usage
            try:
                proc = psutil.Process()
                result["memory_mb"] = round(proc.memory_info().rss / 1024 / 1024, 1)
            except Exception:
                pass

            if result.get("database") == "error":
                result["status"] = "degraded"

        return result

    # Auth dependency for all protected admin routes
    admin_auth_dep = [Depends(get_current_admin)]

    # Auth routes (public — no auth required)
    app.include_router(
        admin_auth.router,
        prefix="/api/v1/auth",
        tags=["Auth"]
    )

    # Protected admin routes
    app.include_router(
        clients.router,
        prefix="/api/v1/clients",
        tags=["Clients"],
        dependencies=admin_auth_dep
    )

    app.include_router(
        servers.router,
        prefix="/api/v1/servers",
        tags=["Servers"],
        dependencies=admin_auth_dep
    )

    app.include_router(
        bots.router,
        prefix="/api/v1/bots",
        tags=["Bots"],
        dependencies=admin_auth_dep
    )

    app.include_router(
        payments.router,
        prefix="/api/v1/payments",
        tags=["Payments"],
        dependencies=admin_auth_dep
    )

    app.include_router(
        system.router,
        prefix="/api/v1/system",
        tags=["System"],
        dependencies=admin_auth_dep
    )

    app.include_router(
        agent.router,
        prefix="/api/v1/agent",
        tags=["Agent"],
        dependencies=admin_auth_dep
    )

    app.include_router(
        tariffs.router,
        prefix="/api/v1/tariffs",
        tags=["Tariffs"],
        dependencies=admin_auth_dep
    )

    app.include_router(
        traffic_rules.router,
        prefix="/api/v1/traffic",
        tags=["Traffic Rules"],
        dependencies=admin_auth_dep
    )

    app.include_router(
        portal_users.router,
        prefix="/api/v1/portal-users",
        tags=["Portal Users"],
        dependencies=admin_auth_dep
    )

    app.include_router(
        promo_codes.router,
        prefix="/api/v1/promo-codes",
        tags=["Promo Codes"],
        dependencies=admin_auth_dep
    )

    app.include_router(
        app_accounts.router,
        prefix="/api/v1/app-accounts",
        tags=["App Accounts"],
        dependencies=admin_auth_dep
    )

    app.include_router(
        backup.router,
        prefix="/api/v1/backup",
        tags=["Backup"],
        dependencies=admin_auth_dep
    )

    app.include_router(
        updates.router,
        prefix="/api/v1/updates",
        tags=["Updates"],
        dependencies=admin_auth_dep
    )

    # Plugin management — install/uninstall arbitrary user plugins from URL.
    # Auth is enforced inside the route via Depends(get_current_admin).
    app.include_router(
        plugins_admin.router,
        tags=["Plugins"],
    )

    app.include_router(
        health.router,
        prefix="/api/v1/health",
        tags=["Health"],
        dependencies=admin_auth_dep
    )

    # Public branding endpoint (no auth — needed by login pages and client portal)
    from .routes.system import router as system_router_ref
    from fastapi import APIRouter
    public_router = APIRouter()

    @public_router.get("/branding")
    async def public_branding(db: Session = Depends(get_db)):
        from ..modules.branding import get_all_branding
        return get_all_branding(db)

    app.include_router(
        public_router,
        prefix="/api/v1/public",
        tags=["Public"]
    )

    # Client portal (has its own JWT auth, not admin auth)
    app.include_router(
        client_portal.router,
        tags=["Client Portal"]
    )

    # Corporate VPN — client portal routes (portal JWT auth)
    app.include_router(
        corporate.portal_router,
        prefix="/client-portal/corporate",
        tags=["Corporate VPN"],
    )

    # Corporate VPN — admin routes (admin JWT auth)
    app.include_router(
        corporate.admin_router,
        prefix="/api/v1/corporate",
        tags=["Corporate VPN Admin"],
        dependencies=admin_auth_dep,
    )

    # Internal API (protected by service token, not admin auth)
    app.include_router(
        internal.router,
        prefix="/api/v1/internal",
        tags=["Internal"]
    )

    # Generic plugin loader — runs at create_app() time (not lifespan!) so plugin
    # routers are inserted into app.routes BEFORE the SPA catch-all below. If we
    # ran this in lifespan, the catch-all would already be ahead of plugin
    # routes and would 404 every plugin URL.
    try:
        from ..modules.plugin_loader import PluginLoader
        from ..modules.license.manager import get_license_manager
        from pathlib import Path as _P
        _plugins_root = _P(__file__).resolve().parents[2] / "plugins"
        _loader = PluginLoader(_plugins_root)
        _records = _loader.discover_and_load(
            license_manager=get_license_manager(),
            fastapi_app=app,
        )
        _loaded_count = sum(1 for r in _records if r.loaded)
        _skipped_count = sum(1 for r in _records if r.skipped)
        if _loaded_count or _skipped_count:
            logger.info(
                "Plugin loader: {} loaded, {} skipped (license)",
                _loaded_count, _skipped_count,
            )
        app.state.plugin_loader = _loader
    except Exception as _ple:
        import traceback
        logger.warning(
            "Generic plugin loader failed: {}\n{}",
            _ple, traceback.format_exc(),
        )

    # Serve uploaded branding assets (logos, favicons)
    uploads_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web", "static")
    if os.path.isdir(uploads_dir):
        app.mount("/static", StaticFiles(directory=uploads_dir), name="static_uploads")

    # Serve Vue.js SPA static files (built output)
    static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web", "static", "dist")
    if os.path.isdir(static_dir):
        # Serve static assets (js, css, images)
        assets_dir = os.path.join(static_dir, "assets")
        if os.path.isdir(assets_dir):
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

        index_path = os.path.join(static_dir, "index.html")

        # No-cache headers for index.html to prevent stale SPA shell
        no_cache_headers = {
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        }

        @app.get("/", include_in_schema=False)
        async def serve_spa_root():
            return FileResponse(index_path, headers=no_cache_headers)

        # Catch-all for SPA client-side routing (must be last)
        @app.get("/{full_path:path}", include_in_schema=False)
        async def serve_spa(full_path: str):
            # Don't intercept API or docs routes
            if full_path.startswith("api/") or full_path.startswith("health"):
                raise HTTPException(status_code=404)

            # Serve APK download
            if full_path == "download/app":
                apk_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web", "static", "vpn-manager.apk")
                if os.path.isfile(apk_path):
                    return FileResponse(apk_path, filename="vpn-manager.apk", media_type="application/vnd.android.package-archive")
                raise HTTPException(status_code=404, detail="APK not found")

            # Try to serve the file directly first (with path traversal guard)
            file_path = os.path.join(static_dir, full_path)
            if not os.path.abspath(file_path).startswith(os.path.abspath(static_dir)):
                raise HTTPException(status_code=404)
            if os.path.isfile(file_path):
                return FileResponse(file_path)

            # Fall back to index.html for client-side routing
            return FileResponse(index_path, headers=no_cache_headers)
    else:
        @app.get("/", tags=["System"])
        async def root():
            """Root endpoint (no frontend built yet)"""
            return {
                "name": "VPN Manager API",
                "version": version,
                "docs": "/api/docs",
                "note": "Run 'npm run build' in src/web/frontend/ to enable the web panel",
            }

    return app


# Create default application instance
app = create_app()


def run_server(
    host: str = "0.0.0.0",
    port: int = 10086,
    reload: bool = False,
    workers: int = 1,
):
    """
    Run the API server using uvicorn

    Args:
        host: Host to bind to
        port: Port to listen on
        reload: Enable auto-reload (development)
        workers: Number of worker processes
    """
    import uvicorn

    # Configure logging
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="INFO",
    )

    logger.info(f"Starting server on {host}:{port}")

    uvicorn.run(
        "src.api.main:app",
        host=host,
        port=port,
        reload=reload,
        workers=workers,
    )


if __name__ == "__main__":
    run_server(reload=True)
