from __future__ import annotations

import argparse
import getpass

from app.auth.local_auth_service import LocalAuthService
from app.db import default_database


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a local Auralys user account.")
    parser.add_argument("--username", required=True)
    parser.add_argument("--role", required=True, choices=["sav", "ceo"])
    parser.add_argument("--display-name", default=None)
    parser.add_argument("--email", default=None)
    args = parser.parse_args()

    password = getpass.getpass("Password: ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        raise SystemExit("Passwords do not match.")

    service = LocalAuthService(database=default_database)
    user = service.create_user(
        username=args.username,
        password=password,
        role=args.role,
        display_name=args.display_name,
        email=args.email,
    )
    print(f"Created user: {user}")


if __name__ == "__main__":
    main()
