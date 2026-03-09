import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, scoped_session, sessionmaker

load_dotenv()

_raw_database_url = os.getenv("DATABASE_URL")
DATABASE_URL: str = _raw_database_url if _raw_database_url else "sqlite:///scrapai.db"

engine = create_engine(DATABASE_URL)


@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    if "sqlite" in DATABASE_URL:
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA cache_size=-64000")
        cursor.close()


def is_postgres() -> bool:
    return "postgresql" in DATABASE_URL or "postgres" in DATABASE_URL


def is_sqlite() -> bool:
    return "sqlite" in DATABASE_URL


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

db_session = scoped_session(SessionLocal)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    import core.models  # noqa: F401 - needed to register models with SQLAlchemy

    Base.metadata.create_all(bind=engine)
