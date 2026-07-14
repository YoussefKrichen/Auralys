from __future__ import annotations

from app.db.postgres import PostgresDatabase


Database = PostgresDatabase
default_database = PostgresDatabase()


__all__ = ["Database", "PostgresDatabase", "default_database"]
