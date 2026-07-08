from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from psycopg import Connection

from app.db.postgres import PostgresDatabase


Database = PostgresDatabase
default_database = PostgresDatabase()


@contextmanager
def get_connection(dsn: str | None = None) -> Iterator[Connection]:
    database = default_database if dsn is None else PostgresDatabase(dsn=dsn)
    with database.connection() as connection:
        yield connection


def init_db(dsn: str | None = None) -> None:
    database = default_database if dsn is None else PostgresDatabase(dsn=dsn)
    database.initialize_schema()


__all__ = ["Database", "PostgresDatabase", "default_database", "get_connection", "init_db"]
