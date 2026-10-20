"""Administrative local account utility for migrated learner identities."""

import argparse
import getpass
import re

from src.auth import AuthService


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage a local T2P account.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    set_password = subparsers.add_parser(
        "set-password", help="Set or reset a migrated user's password."
    )
    set_password.add_argument("user_id")
    set_role = subparsers.add_parser("set-role", help="Set an existing local account's course administration role.")
    set_role.add_argument("user_id")
    set_role.add_argument("role", choices=["student", "admin"])
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", args.user_id):
        raise SystemExit("Invalid user ID.")

    if args.command == "set-role":
        from scripts.backup_local import backup
        from src.database import get_database
        from src.database.models import User
        backup()
        with get_database().session() as session:
            account = session.get(User, args.user_id)
            if account is None:
                raise SystemExit("Account not found. Register it in the app first.")
            account.role = args.role
        print(f"Role updated for {args.user_id}. Sign out and sign in again to refresh the UI.")

    if args.command == "set-password":
        password = getpass.getpass("New password: ")
        confirmation = getpass.getpass("Confirm password: ")
        if password != confirmation:
            raise SystemExit("Passwords do not match.")
        AuthService().set_password(args.user_id, password)
        print(f"Password updated for {args.user_id}.")


if __name__ == "__main__":
    main()
