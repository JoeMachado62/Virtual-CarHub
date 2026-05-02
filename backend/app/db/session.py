from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

engine_kwargs: dict = {
    "echo": False,
    "future": True,
}
engine_kwargs.update(
    {
        "pool_pre_ping": True,
        "pool_size": max(1, settings.database_pool_size),
        "max_overflow": max(0, settings.database_max_overflow),
        "pool_timeout": max(1, settings.database_pool_timeout_seconds),
        "pool_recycle": max(30, settings.database_pool_recycle_seconds),
    }
)

engine = create_engine(settings.database_url, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
