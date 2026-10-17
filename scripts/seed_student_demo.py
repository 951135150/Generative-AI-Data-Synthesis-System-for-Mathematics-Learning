"""Back up SQLite and restore the deterministic student_01 interview record."""

import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from src.config import Config
from src.database.core import Database
from src.demo_progress import DEMO_USER_ID, apply_demo_progress


def sqlite_path_from_url(database_url: str) -> Path:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise RuntimeError(
            "The demo seed currently supports the local SQLite interview profile only."
        )
    return Path(database_url.removeprefix(prefix)).expanduser().resolve()


def backup_sqlite_database(source_path: Path) -> Path:
    if not source_path.exists():
        raise FileNotFoundError(f"SQLite database not found: {source_path}")
    backup_directory = source_path.parent / "backups"
    backup_directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-%f")
    destination = backup_directory / f"t2p-before-{DEMO_USER_ID}-{timestamp}.db"
    with sqlite3.connect(source_path) as source, sqlite3.connect(destination) as target:
        source.backup(target)
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Restore a credible B-grade Academic Progress Report for an existing demo account."
    )
    parser.add_argument("--user-id", default=DEMO_USER_ID)
    args = parser.parse_args()

    database_path = sqlite_path_from_url(Config.DATABASE_URL)
    backup_path = backup_sqlite_database(database_path)
    summary = apply_demo_progress(Database(Config.DATABASE_URL), args.user_id)
    print(json.dumps({"backup": str(backup_path), "profile": summary}, indent=2))


if __name__ == "__main__":
    main()
