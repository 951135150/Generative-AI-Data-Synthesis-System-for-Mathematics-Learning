"""Import legacy JSON artifacts into any configured SQLAlchemy database."""

import argparse
import json

from src.database import Database
from src.database.migration import LegacyJsonMigrator


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Idempotently import T2P JSON data into SQLite or PostgreSQL."
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="Override DATABASE_URL with a SQLAlchemy connection URL.",
    )
    args = parser.parse_args()
    database = Database(args.database_url) if args.database_url else None
    print(
        json.dumps(
            LegacyJsonMigrator(database=database).run(),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
