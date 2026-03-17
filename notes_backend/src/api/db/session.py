"""
Database session management — async engine and session factory.

Flow: DatabaseSession
Entrypoint: get_db()

Contract:
- Input: None (reads config from environment)
- Output: AsyncSession yielded per request
- Errors: SQLAlchemy connection errors propagate to caller
- Side effects: Opens/closes DB connections

Observability:
- Logs engine creation at startup
- Connection errors surface as 500 to API layer
"""

import os
import logging

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)

# Build the async database URL from individual environment variables.
# We always construct the URL from parts to ensure credentials are included,
# regardless of whether POSTGRES_URL is set (it may lack user/password).
POSTGRES_USER = os.getenv("POSTGRES_USER", "appuser")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "dbuser123")
POSTGRES_DB = os.getenv("POSTGRES_DB", "myapp")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5000")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")

DATABASE_URL = (
    f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
    f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
)

logger.info(
    "Initializing async database engine: host=%s port=%s db=%s user=%s",
    POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER,
)

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
