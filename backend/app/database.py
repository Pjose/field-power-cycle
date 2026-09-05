import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Real Postgres by default now, matching a real deployment target. Falls
# back to a local SQLite file only if FPC_DATABASE_URL is explicitly unset
# AND FPC_ALLOW_SQLITE_FALLBACK=1 is set — this is meant to make the
# fallback a deliberate opt-in for local/offline development, not a silent
# default that quietly diverges from what production actually runs on.
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fieldpowercycle.db")

DATABASE_URL = os.environ.get("FPC_DATABASE_URL")
if not DATABASE_URL:
    if os.environ.get("FPC_ALLOW_SQLITE_FALLBACK") == "1":
        DATABASE_URL = f"sqlite:///{DB_PATH}"
    else:
        DATABASE_URL = "postgresql+psycopg://fpc_app:fpc_dev_password@localhost:5432/fieldpowercycle"

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
