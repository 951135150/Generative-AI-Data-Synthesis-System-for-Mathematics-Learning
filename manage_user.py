"""Administrative local account utility for migrated learner identities."""

import argparse
import getpass

from src.auth import AuthService


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage a local T2P account.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    set_password = subparsers.add_parser(
        "set-password", help="Set or reset a migrated user's password."
    )
    set_password.add_argument("user_id")
    args = parser.parse_args()

    if args.command == "set-password":
        password = getpass.getpass("New password: ")
        confirmation = getpass.getpass("Confirm password: ")
        if password != confirmation:
            raise SystemExit("Passwords do not match.")
        AuthService().set_password(args.user_id, password)
        print(f"Password updated for {args.user_id}.")


if __name__ == "__main__":
    main()
