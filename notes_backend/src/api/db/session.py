"""
Database session management — async engine and session factory.

Flow: DatabaseSession
Entrypoint: get_db()

Contract:
- Input: None (reads config from environment at module load)
- Output: AsyncSession yielded per request
- Errors: SQLAlchemy connection errors propagate to caller
- Side effects: Opens/closes DB connections

Configuration priority:
1. Always build URL from individual POSTGRES_* env vars (USER, PASSWORD, HOST, PORT, DB).
   This is the most reliable approach because POSTGRES_URL may lack credentials.
2. POSTGRES_URL is only used as a fallback if individual vars are missing,
   and credentials from POSTGRES_USER/POSTGRES_PASSWORD are injected when absent.

Observability:
- Logs engine creation at startup (host, port, db, user — no password)
- Connection errors surface as 500 to API layer

How to debug:
1. Check the log line "Initializing async database engine: ..." for the URL (sans password).
2. Verify POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB, POSTGRES_PORT, POSTGRES_HOST env vars.
3. Ensure PostgreSQL is reachable at the logged host:port.
"""

import os
import logging
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)


def _build_database_url() -> str:
    """
    Build the async database URL from environment variables.

    Strategy:
    - Read individual POSTGRES_* vars (USER, PASSWORD, HOST, PORT, DB).
    - If all required individual vars are available, build URL from them
      (this is the most reliable path since POSTGRES_URL often lacks credentials).
    - If individual vars are incomplete, try POSTGRES_URL and inject missing
      credentials from POSTGRES_USER / POSTGRES_PASSWORD.
    - Final fallback: hardcoded development defaults.

    Returns:
        Async-compatible PostgreSQL connection string.

    Invariants:
    - The returned URL always starts with 'postgresql+asyncpg://'.
    - The URL always contains user:password if available from env.
    """
    pg_user = os.getenv("POSTGRES_USER", "")
    pg_password = os.getenv("POSTGRES_PASSWORD", "")
    pg_db = os.getenv("POSTGRES_DB", "")
    pg_port = os.getenv("POSTGRES_PORT", "")
    pg_host = os.getenv("POSTGRES_HOST", "")

    # Path 1: Build from individual vars when we have at least user + password
    if pg_user and pg_password:
        host = pg_host or "localhost"
        port = pg_port or "5000"
        db = pg_db or "myapp"
        url = (
            f"postgresql+asyncpg://{pg_user}:{pg_password}"
            f"@{host}:{port}/{db}"
        )
        logger.info(
            "DB URL built from individual env vars: user=%s host=%s port=%s db=%s",
            pg_user, host, port, db,
        )
        return url

    # Path 2: Try POSTGRES_URL and inject credentials if missing
    postgres_url = os.getenv("POSTGRES_URL", "")
    if postgres_url:
        parsed = urlparse(postgres_url.strip())

        # Determine credentials: prefer individual env vars, then parsed, then defaults
        user = pg_user or parsed.username or "appuser"
        password = pg_password or parsed.password or "dbuser123"
        host = pg_host or parsed.hostname or "localhost"
        port = pg_port or str(parsed.port or 5000)
        db = pg_db or (parsed.path.lstrip("/") if parsed.path else "myapp")

        url = (
            f"postgresql+asyncpg://{user}:{password}"
            f"@{host}:{port}/{db}"
        )
        logger.info(
            "DB URL built from POSTGRES_URL + env overrides: user=%s host=%s port=%s db=%s",
            user, host, port, db,
        )
        return url

    # Path 3: Hardcoded development defaults (last resort)
    logger.warning(
        "No POSTGRES_* env vars found; using hardcoded development defaults. "
        "Set POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB in .env."
    )
    return "postgresql+asyncpg://appuser:dbuser123@localhost:5000/myapp"


DATABASE_URL = _build_database_url()

# Log connection info (never log password)
_safe_url = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
logger.info("Async database engine target: %s", _safe_url)

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# PUBLIC_INTERFACE
async def get_db():
    """
    FastAPI dependency that yields an async database session.

    Usage:
        @app.get("/example")
        async def example(db: AsyncSession = Depends(get_db)):
            ...

    The session is automatically closed after the request completes.
    """
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()
