import os
from contextlib import contextmanager
from pathlib import Path
from typing import Generator
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.db.models import Base
from src.utils.logging_config import setup_logger

load_dotenv()

logger = setup_logger("quant_nifty.db")

_engine = None
_SessionFactory = None

def get_database_url() -> str:
    """Returns PostgreSQL connection string from environment if set, else falls back to SQLite."""
    db_url = os.getenv("DATABASE_URL")
    if db_url and db_url.strip():
        # Clean postgres:// to postgresql:// for SQLAlchemy compatibility if needed
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        return db_url.strip()

    # Fallback to local SQLite
    db_dir = Path("data/raw")
    db_dir.mkdir(parents=True, exist_ok=True)
    sqlite_path = db_dir / "market_data.db"
    return f"sqlite:///{sqlite_path.as_posix()}"

def get_engine():
    """Returns global database engine (PostgreSQL or SQLite)."""
    global _engine
    if _engine is None:
        url = get_database_url()
        is_sqlite = url.startswith("sqlite")
        masked_url = url.split("@")[-1] if "@" in url else url
        logger.info(f"Connecting to database: {masked_url} ({'SQLite' if is_sqlite else 'PostgreSQL'})")

        if is_sqlite:
            _engine = create_engine(url, echo=False)
        else:
            _engine = create_engine(
                url,
                echo=False,
                pool_pre_ping=True,
                pool_size=5,
                max_overflow=10,
            )
    return _engine

def init_db():
    """Initializes database schema and creates all tables."""
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables verified/initialized.")

def get_session_factory():
    """Returns sessionmaker bound to engine."""
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)
    return _SessionFactory

@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """Context manager for safe transactional database sessions."""
    session_factory = get_session_factory()
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Database session error: {e}")
        raise
    finally:
        session.close()
