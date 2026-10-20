"""Consistent SQLite backup; never print credentials or mutate source data."""
import sqlite3
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def backup():
    import sys
    sys.path.insert(0, str(ROOT))
    from src.config import Config
    from sqlalchemy.engine import make_url
    database_url = make_url(Config.DATABASE_URL)
    if database_url.get_backend_name() != "sqlite" or not database_url.database or database_url.database == ":memory:":
        print("No file-backed SQLite database to back up.")
        return None
    source = Path(database_url.database).resolve()
    if not source.exists():
        return None
    folder = source.parent / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"pre_rag_{datetime.now():%Y%m%d_%H%M%S_%f}.db"
    with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as original:
        with sqlite3.connect(target) as destination:
            original.backup(destination)
    print(f"SQLite backup: {target}")
    return target


if __name__ == "__main__":
    backup()
