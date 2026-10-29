from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings  = get_settings()

engine = create_async_engine(settings.database_url,echo=settings.debug,
                             pool_pre_ping=True,#连接失效前先探话，避免mysql 8小时断开后报Lost connection
                             pool_recycle=3600,#每小时回收连接，配合mysql 默认wait_timeout = 28800
                             pool_size=10,
                             max_overflow=20)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


async def get_db():
    async with SessionLocal() as session:
        yield session
