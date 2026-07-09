from __future__ import annotations

from typing import Any

import bcrypt

from app.db import Database, default_database

# Fixed demo credentials, checked before the database so login keeps working
# even when Postgres is unreachable. Not meant for production use.
_STATIC_CREDENTIALS: dict[str, dict[str, Any]] = {
    "ceo": {"id": -1, "password": "ceo123", "role": "ceo", "display_name": "CEO"},
    "sav": {"id": -2, "password": "sav123", "role": "sav", "display_name": "SAV"},
}


class LocalAuthService:
    def __init__(self, database: Database | None = None) -> None:
        self.database = database or default_database

    def create_user(
        self,
        *,
        username: str,
        password: str,
        role: str,
        display_name: str | None = None,
        email: str | None = None,
    ) -> dict[str, Any]:
        normalized_username = username.strip().lower()
        if not normalized_username or not password:
            raise ValueError("Username and password are required.")
        self.database.init_schema()
        if self.database.fetch_user_by_username(normalized_username):
            raise ValueError(f"User `{normalized_username}` already exists.")

        password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")
        with self.database.connection() as connection:
            user_id = self.database.insert_user(
                connection,
                username=normalized_username,
                password_hash=password_hash,
                role=role,
                display_name=display_name or normalized_username,
                email=email,
            )
        return {
            "id": user_id,
            "username": normalized_username,
            "role": role,
            "display_name": display_name or normalized_username,
        }

    def authenticate(self, username: str, password: str) -> dict[str, Any] | None:
        normalized_username = username.strip().lower()
        if not normalized_username or not password:
            return None

        static_user = _STATIC_CREDENTIALS.get(normalized_username)
        if static_user and password == static_user["password"]:
            return {
                "id": static_user["id"],
                "username": normalized_username,
                "role": static_user["role"],
                "display_name": static_user["display_name"],
            }

        self.database.init_schema()
        user = self.database.fetch_user_by_username(normalized_username)
        if user is None or not user.get("is_active", True):
            return None
        if not bcrypt.checkpw(password.encode("utf-8"), user["password_hash"].encode("utf-8")):
            return None
        return {
            "id": user["id"],
            "username": user["username"],
            "role": user["role"],
            "display_name": user["display_name"] or user["username"],
        }
