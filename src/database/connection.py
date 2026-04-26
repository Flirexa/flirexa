"""
VPN Management Studio Database Connection
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
    engine = create_engine(
        DATABASE_URL,
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=1800,
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
        async_engine = create_async_engine(
            ASYNC_DATABASE_URL,
            pool_size=5,
            max_overflow=10,
            pool_timeout=30,
            pool_recycle=1800,
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

def _run_alembic_migrations() -> None:
    """Run Alembic migrations to bring schema up to date."""
    import logging
    log = logging.getLogger(__name__)
    try:
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
        log.warning("Alembic migration failed (non-fatal, app will still start): %s", e)


def init_db() -> None:
    """
    Initialize database - create all tables
    Call this at application startup
    """
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
