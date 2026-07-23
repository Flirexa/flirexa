"""
Flirexa Database Connection
Handles database connections for both sync and async operations
"""

import os
from typing import Generator, AsyncGenerator
from contextlib import contextmanager, asynccontextmanager

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool

from .models import Base

# Database configuration from environment or defaults
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://vpnmanager:vpnmanager@localhost:5432/vpnmanager_db"
)

# For async operations
ASYNC_DATABASE_URL = DATABASE_URL.replace(
    "postgresql://", "postgresql+asyncpg://"
).replace(
    "postgres://", "postgresql+asyncpg://"
)

# SQLite support for development/testing
if "sqlite" in DATABASE_URL:
    ASYNC_DATABASE_URL = DATABASE_URL.replace("sqlite://", "sqlite+aiosqlite://")


# ============================================================================
# SYNC ENGINE & SESSION
# ============================================================================

# Check if using SQLite (for in-memory/testing)
is_sqlite = "sqlite" in DATABASE_URL

if is_sqlite:
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=os.getenv("SQL_ECHO", "false").lower() == "true",
    )
else:
    # Pool sizing tuned for FastAPI's default 40-thread threadpool.
    # Each uvicorn worker process keeps its own pool of size
    # DB_POOL_SIZE + DB_MAX_OVERFLOW, so total connections =
    # API_WORKERS * (pool_size + max_overflow). Defaults (20 + 30 = 50)
    # leave headroom under Postgres default max_connections=100 when
    # API_WORKERS=1; operators bumping workers must raise both
    # max_connections AND reduce per-worker pool or set the env vars
    # explicitly (e.g. DB_POOL_SIZE=10 DB_MAX_OVERFLOW=15 for 4 workers
    # against a 100-connection Postgres).
    # Auto-size the per-worker pool when the API runs multi-worker.
    # run_server() resolves the worker count (hardware-aware) and publishes it
    # as VPNM_RESOLVED_WORKERS before uvicorn spawns the workers. With N > 1
    # we split a global connection budget (default 80, i.e. Postgres
    # max_connections=100 minus headroom for the worker/portal services)
    # evenly across workers so N × (pool + overflow) can't blow past PG.
    # Explicit DB_POOL_SIZE / DB_MAX_OVERFLOW always win; N == 1 keeps the
    # long-standing 20 + 30 defaults unchanged.
    _n_workers = int(os.getenv("VPNM_RESOLVED_WORKERS") or 1)
    if _n_workers > 1 and not (os.getenv("DB_POOL_SIZE") or os.getenv("DB_MAX_OVERFLOW")):
        _budget = int(os.getenv("DB_CONN_BUDGET") or 80)
        _per_worker = max(10, _budget // _n_workers)
        _auto_pool = max(5, _per_worker // 2)
        _pool_size = _auto_pool
        _max_overflow = max(5, _per_worker - _auto_pool)
    else:
        _pool_size     = int(os.getenv("DB_POOL_SIZE")     or 20)
        _max_overflow  = int(os.getenv("DB_MAX_OVERFLOW")  or 30)
    # pool_pre_ping=True does a SELECT 1 round-trip on every checkout
    # to catch connections killed by a Postgres restart. Cheap when one
    # request acquires one connection. Painful under thread-pool fan-out:
    # py-spy on 2026-06-11 caught the api worker parked inside
    # _do_ping_w_event with multiple AnyIO threads queued for the lock.
    # Set DB_POOL_PRE_PING=false on perf-tuned deploys and rely on
    # pool_recycle to refresh stale connections; cost is one 500 on
    # the first request after a Postgres restart, then back to normal.
    _pre_ping      = (os.getenv("DB_POOL_PRE_PING", "true") or "true").lower() != "false"
    engine = create_engine(
        DATABASE_URL,
        pool_size=_pool_size,
        max_overflow=_max_overflow,
        pool_timeout=10,
        pool_recycle=1800,
        pool_pre_ping=_pre_ping,
        echo=os.getenv("SQL_ECHO", "false").lower() == "true",
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ============================================================================
# ASYNC ENGINE & SESSION
# ============================================================================

try:
    if is_sqlite:
        async_engine = create_async_engine(
            ASYNC_DATABASE_URL,
            echo=os.getenv("SQL_ECHO", "false").lower() == "true",
        )
    else:
        # Match sync engine pool. Async path is used by background workers
        # and websocket handlers, which can be just as concurrent as HTTP.
        async_engine = create_async_engine(
            ASYNC_DATABASE_URL,
            pool_size=_pool_size,
            max_overflow=_max_overflow,
            pool_timeout=10,
            pool_recycle=1800,
            pool_pre_ping=_pre_ping,
            echo=os.getenv("SQL_ECHO", "false").lower() == "true",
        )

    AsyncSessionLocal = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )
except Exception:
    # Async driver not available (e.g. during testing without aiosqlite/asyncpg)
    async_engine = None
    AsyncSessionLocal = None


# ============================================================================
# DEPENDENCY FUNCTIONS
# ============================================================================

def get_db() -> Generator[Session, None, None]:
    """
    Get sync database session (dependency injection for FastAPI)
    Usage:
        @app.get("/items")
        def get_items(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        # Roll back a failed transaction before the connection returns to the
        # pool. Without this, a route that catches its own error and keeps
        # using `db` (several portal endpoints commit after partial work) can
        # leave the session in an aborted-transaction state, so the NEXT
        # pooled user hits "current transaction is aborted". We do NOT commit
        # here — routes commit explicitly; only the cleanup is centralised.
        db.rollback()
        raise
    finally:
        db.close()


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Get async database session (dependency injection for FastAPI)
    Usage:
        @app.get("/items")
        async def get_items(db: AsyncSession = Depends(get_async_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


@contextmanager
def get_db_context() -> Generator[Session, None, None]:
    """
    Context manager for sync database session
    Usage:
        with get_db_context() as db:
            db.query(...)
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@asynccontextmanager
async def get_async_db_context() -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager for async database session
    Usage:
        async with get_async_db_context() as db:
            await db.execute(...)
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ============================================================================
# INITIALIZATION FUNCTIONS
# ============================================================================

def _register_all_model_metadata() -> None:
    """Load models declared outside ``src.database.models``.

    ``FcmToken`` and the corporate tables reference ``client_users``, which is
    declared in the subscription module.  CLI-driven fresh installs import the
    connection layer directly (without importing the FastAPI routes first), so
    those tables must be registered explicitly before ``create_all()`` sorts
    foreign keys.
    """
    from ..modules.subscription import subscription_models as _subscription_models  # noqa: F401
    from ..modules.corporate import models as _corporate_models  # noqa: F401


def _run_alembic_migrations() -> None:
    """Run Alembic migrations to bring schema up to date."""
    import logging
    log = logging.getLogger(__name__)
    try:
        _register_all_model_metadata()

        from alembic.config import Config
        from alembic import command
        import os

        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        alembic_ini = os.path.join(project_root, "alembic.ini")

        if not os.path.exists(alembic_ini):
            log.warning("alembic.ini not found at %s, skipping Alembic migrations", alembic_ini)
            return

        alembic_cfg = Config(alembic_ini)
        alembic_cfg.set_main_option("sqlalchemy.url", DATABASE_URL)

        # Stamp if no version table exists (first time on existing DB)
        from alembic.runtime.migration import MigrationContext
        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            current_rev = ctx.get_current_revision()
            existing_tables = {name for name in inspect(conn).get_table_names() if name != "alembic_version"}

        if current_rev is None:
            if not existing_tables:
                log.info("Fresh database detected, creating schema from models and stamping Alembic head...")
                Base.metadata.create_all(bind=engine)
                command.stamp(alembic_cfg, "head")
                return

            log.info("Existing database without Alembic version found, stamping baseline (001)...")
            command.stamp(alembic_cfg, "001")

        # Upgrade to head
        command.upgrade(alembic_cfg, "head")
        log.info("Alembic migrations applied successfully")
    except Exception as e:
        # Log the FULL traceback at ERROR level. The previous "warning + str(e)"
        # made post-update Alembic mismatches invisible: smoke checks still
        # detected the version-skew and triggered rollbacks, but operators
        # had no idea WHY the migration failed. With the traceback in
        # journalctl, the next failure is at most a `journalctl -u …
        # | grep "Alembic migration failed"` away.
        log.error("Alembic migration failed: %s", e, exc_info=True)
        raise


def init_db() -> None:
    """
    Initialize database - create all tables
    Call this at application startup
    """
    _register_all_model_metadata()

    if is_sqlite:
        Base.metadata.create_all(bind=engine)
        return

    # For production databases Alembic is the single source of truth.
    # Running create_all() first causes fresh installs to materialize the
    # latest ORM schema and then re-apply historical migrations on top,
    # which breaks deterministic install/upgrade behavior.
    _run_alembic_migrations()


async def init_async_db() -> None:
    """
    Initialize database asynchronously
    """
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def close_db() -> None:
    """
    Close database connections
    Call this at application shutdown
    """
    engine.dispose()


async def close_async_db() -> None:
    """
    Close async database connections
    """
    await async_engine.dispose()


# ============================================================================
# HEALTH CHECK
# ============================================================================

def check_db_connection() -> bool:
    """Check if database is accessible"""
    try:
        with get_db_context() as db:
            from sqlalchemy import text
            db.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def check_async_db_connection() -> bool:
    """Check if database is accessible (async)"""
    try:
        async with get_async_db_context() as db:
            from sqlalchemy import text
            await db.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
