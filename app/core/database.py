from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import get_settings

_settings = get_settings()

# Async engine — used by FastAPI request handlers
engine = create_async_engine(
    _settings.database_url,
    pool_pre_ping=True,
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Sync engine — used by RQ workers (same DB, sync driver)
# asyncpg is async-only; swap to psycopg2 for the sync URL.
_sync_url = _settings.database_url.replace(
    "postgresql+asyncpg://", "postgresql+psycopg2://"
)

_sync_engine = create_engine(_sync_url, pool_pre_ping=True)

SyncSessionLocal = sessionmaker(bind=_sync_engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass
