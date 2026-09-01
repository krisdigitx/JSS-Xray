from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import settings

connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args["check_same_thread"] = False
elif settings.database_url.startswith("postgresql"):
    # Safeguards against sessions remaining idle in a transaction forever.
    # statement_timeout protects normal app requests; migrations override it.
    connect_args["options"] = (
        "-c statement_timeout=30000 "
        "-c lock_timeout=5000 "
        "-c idle_in_transaction_session_timeout=60000"
    )

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=1800,
    connect_args=connect_args,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        # Explicit rollback guarantees any implicit read transaction is ended
        # before the connection is returned to SQLAlchemy's pool.
        try:
            db.rollback()
        finally:
            db.close()
