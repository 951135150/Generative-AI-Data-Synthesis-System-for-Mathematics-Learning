"""Database engine and transaction boundaries."""

from contextlib import contextmanager
from pathlib import Path
from threading import Lock
from typing import Iterator, Optional

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.config import Config
from src.database.models import Base


SCHEMA_VERSION = 3


class Database:
    """Small SQLAlchemy facade with safe SQLite defaults."""

    def __init__(self, url: Optional[str] = None):
        self.url = url or Config.DATABASE_URL
        self._prepare_sqlite_directory()
        connect_args = (
            {"check_same_thread": False, "timeout": 30}
            if self.url.startswith("sqlite")
            else {}
        )
        self.engine: Engine = create_engine(
            self.url, future=True, pool_pre_ping=True, connect_args=connect_args
        )
        if self.url.startswith("sqlite"):
            event.listen(self.engine, "connect", self._configure_sqlite)
        self.SessionLocal = sessionmaker(
            bind=self.engine, autoflush=False, expire_on_commit=False, future=True
        )
        self.initialize()

    def _prepare_sqlite_directory(self) -> None:
        prefix = "sqlite:///"
        if self.url.startswith(prefix):
            raw_path = self.url[len(prefix):]
            if raw_path and raw_path != ":memory:":
                Path(raw_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _configure_sqlite(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()

    def initialize(self) -> None:
        Base.metadata.create_all(self.engine)
        self._upgrade_legacy_user_table()
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS schema_migrations "
                    "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
                )
            )
            exists = connection.scalar(
                text("SELECT 1 FROM schema_migrations WHERE version = :version"),
                {"version": SCHEMA_VERSION},
            )
            if not exists:
                connection.execute(
                    text(
                        "INSERT INTO schema_migrations(version, applied_at) "
                        "VALUES (:version, CURRENT_TIMESTAMP)"
                    ),
                    {"version": SCHEMA_VERSION},
                )

    def _upgrade_legacy_user_table(self) -> None:
        """Add authentication columns to databases created before schema v2."""
        inspector = inspect(self.engine)
        if "users" not in inspector.get_table_names():
            return
        existing = {column["name"] for column in inspector.get_columns("users")}
        dialect = self.engine.dialect.name
        boolean_default = "TRUE" if dialect == "postgresql" else "1"
        additions = {
            "password_hash": "VARCHAR(256)",
            "password_salt": "VARCHAR(128)",
            "password_iterations": "INTEGER",
            "role": "VARCHAR(40) NOT NULL DEFAULT 'student'",
            "is_active": f"BOOLEAN NOT NULL DEFAULT {boolean_default}",
        }
        with self.engine.begin() as connection:
            for name, definition in additions.items():
                if name not in existing:
                    connection.execute(
                        text(f"ALTER TABLE users ADD COLUMN {name} {definition}")
                    )

    @contextmanager
    def session(self) -> Iterator[Session]:
        db_session = self.SessionLocal()
        try:
            yield db_session
            db_session.commit()
        except Exception:
            db_session.rollback()
            raise
        finally:
            db_session.close()


_database: Optional[Database] = None
_database_lock = Lock()


def get_database() -> Database:
    global _database
    if _database is None:
        with _database_lock:
            if _database is None:
                _database = Database()
    return _database
