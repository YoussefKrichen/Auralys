from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any, Iterator

import psycopg
from psycopg.rows import dict_row

from app.config import settings


CORE_SCHEMA_STATEMENTS: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS fiches (
        fiche_id TEXT PRIMARY KEY,
        source_file TEXT NOT NULL,
        page_key TEXT NOT NULL,
        client TEXT,
        maintenance_number TEXT,
        service_date DATE,
        service_time TIME,
        service_types JSONB NOT NULL DEFAULT '[]'::jsonb,
        searchable_text TEXT NOT NULL,
        payload JSONB NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS chunks (
        chunk_id TEXT PRIMARY KEY,
        fiche_id TEXT NOT NULL REFERENCES fiches(fiche_id) ON DELETE CASCADE,
        source_file TEXT NOT NULL,
        page_key TEXT NOT NULL,
        chunk_type TEXT NOT NULL,
        ordinal INTEGER NOT NULL DEFAULT 0,
        content TEXT NOT NULL,
        metadata JSONB NOT NULL DEFAULT '{}'::jsonb
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_fiches_client ON fiches (client)",
    "CREATE INDEX IF NOT EXISTS idx_fiches_maintenance_number ON fiches (maintenance_number)",
    "CREATE INDEX IF NOT EXISTS idx_chunks_fiche_id ON chunks (fiche_id)",
    "CREATE INDEX IF NOT EXISTS idx_chunks_chunk_type ON chunks (chunk_type)",
    "CREATE INDEX IF NOT EXISTS idx_chunks_content_fts ON chunks USING GIN (to_tsvector('simple', content))",
    """
    CREATE TABLE IF NOT EXISTS conversations (
        id BIGSERIAL PRIMARY KEY,
        conversation_key TEXT NOT NULL UNIQUE,
        user_id BIGINT,
        role TEXT,
        channel TEXT NOT NULL DEFAULT 'chat',
        status TEXT NOT NULL DEFAULT 'active',
        started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        last_message_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        metadata JSONB NOT NULL DEFAULT '{}'::jsonb
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON conversations (user_id)",
    "CREATE INDEX IF NOT EXISTS idx_conversations_role ON conversations (role)",
    "CREATE INDEX IF NOT EXISTS idx_conversations_last_message_at ON conversations (last_message_at DESC)",
    """
    CREATE TABLE IF NOT EXISTS messages (
        id BIGSERIAL PRIMARY KEY,
        conversation_id BIGINT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
        sender TEXT NOT NULL,
        message_type TEXT NOT NULL DEFAULT 'text',
        content TEXT NOT NULL,
        transcript TEXT,
        audio_path TEXT,
        metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_messages_conversation_id_created_at ON messages (conversation_id, created_at ASC, id ASC)",
    "CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages (sender)",
    """
    CREATE TABLE IF NOT EXISTS memories (
        id BIGSERIAL PRIMARY KEY,
        scope TEXT NOT NULL DEFAULT 'global',
        memory_type TEXT NOT NULL,
        content TEXT NOT NULL,
        source_conversation_id BIGINT REFERENCES conversations(id) ON DELETE SET NULL,
        source_message_id BIGINT REFERENCES messages(id) ON DELETE SET NULL,
        status TEXT NOT NULL DEFAULT 'PENDING',
        confidence DOUBLE PRECISION NOT NULL DEFAULT 0.5,
        tags JSONB NOT NULL DEFAULT '[]'::jsonb,
        metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_memories_status_created_at ON memories (status, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_memories_scope_type ON memories (scope, memory_type)",
    """
    CREATE TABLE IF NOT EXISTS discussion_history (
        history_id BIGSERIAL PRIMARY KEY,
        conversation_id TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        input_type TEXT NOT NULL,
        original_query TEXT NOT NULL,
        transcript TEXT,
        normalized_query TEXT,
        route TEXT,
        intent TEXT,
        filters JSONB NOT NULL DEFAULT '{}'::jsonb,
        answer TEXT NOT NULL,
        response_source TEXT,
        model_output TEXT,
        llm_error TEXT,
        token_usage JSONB NOT NULL DEFAULT '{}'::jsonb,
        timings JSONB NOT NULL DEFAULT '{}'::jsonb,
        spoken_text TEXT,
        hits JSONB NOT NULL DEFAULT '[]'::jsonb,
        reasoning_signals JSONB NOT NULL DEFAULT '{}'::jsonb,
        reasoning_summary TEXT,
        sav_admin_analysis JSONB NOT NULL DEFAULT '{}'::jsonb,
        admin_alert JSONB,
        admin_alert_log_path TEXT,
        output_audio_path TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_discussion_history_conversation_id ON discussion_history (conversation_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_discussion_history_created_at ON discussion_history (created_at DESC)",
    """
    CREATE TABLE IF NOT EXISTS review_cases (
        history_id BIGINT PRIMARY KEY REFERENCES discussion_history(history_id) ON DELETE CASCADE,
        review_status TEXT NOT NULL DEFAULT 'pending',
        decision TEXT,
        review_notes TEXT,
        corrected_answer TEXT,
        knowledge_action TEXT,
        reviewed_by TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        reviewed_at TIMESTAMPTZ
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_review_cases_status_updated_at ON review_cases (review_status, updated_at DESC)",
    """
    CREATE TABLE IF NOT EXISTS users (
        id BIGSERIAL PRIMARY KEY,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL,
        display_name TEXT,
        email TEXT,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
]

_DISCUSSION_HISTORY_COLUMNS = (
    "conversation_id",
    "input_type",
    "original_query",
    "transcript",
    "normalized_query",
    "route",
    "intent",
    "filters",
    "answer",
    "response_source",
    "model_output",
    "llm_error",
    "token_usage",
    "timings",
    "spoken_text",
    "hits",
    "reasoning_signals",
    "reasoning_summary",
    "sav_admin_analysis",
    "admin_alert",
    "admin_alert_log_path",
    "output_audio_path",
)
_DISCUSSION_HISTORY_JSON_COLUMNS = {
    "filters",
    "token_usage",
    "timings",
    "hits",
    "reasoning_signals",
    "sav_admin_analysis",
    "admin_alert",
}


class PostgresDatabase:
    def __init__(self, dsn: str | None = None) -> None:
        self.dsn = dsn or settings.postgres_dsn

    @contextmanager
    def connection(self) -> Iterator[psycopg.Connection]:
        connection = psycopg.connect(self.dsn)
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def init_schema(self) -> None:
        with self.connection() as connection:
            with connection.cursor() as cursor:
                for statement in CORE_SCHEMA_STATEMENTS:
                    cursor.execute(statement)

    def upsert_fiche(self, connection: psycopg.Connection, fiche_row: dict[str, Any]) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO fiches (
                    fiche_id, source_file, page_key, client, maintenance_number,
                    service_date, service_time, service_types, searchable_text, payload
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s::jsonb)
                ON CONFLICT (fiche_id) DO UPDATE SET
                    source_file = EXCLUDED.source_file,
                    page_key = EXCLUDED.page_key,
                    client = EXCLUDED.client,
                    maintenance_number = EXCLUDED.maintenance_number,
                    service_date = EXCLUDED.service_date,
                    service_time = EXCLUDED.service_time,
                    service_types = EXCLUDED.service_types,
                    searchable_text = EXCLUDED.searchable_text,
                    payload = EXCLUDED.payload
                """,
                (
                    fiche_row["fiche_id"],
                    fiche_row["source_file"],
                    fiche_row["page_key"],
                    fiche_row.get("client"),
                    fiche_row.get("maintenance_number"),
                    fiche_row.get("service_date"),
                    fiche_row.get("service_time"),
                    json.dumps(fiche_row.get("service_types") or []),
                    fiche_row["searchable_text"],
                    json.dumps(fiche_row.get("payload") or {}),
                ),
            )

    def upsert_chunk(self, connection: psycopg.Connection, chunk_row: dict[str, Any]) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO chunks (
                    chunk_id, fiche_id, source_file, page_key, chunk_type, ordinal, content, metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (chunk_id) DO UPDATE SET
                    fiche_id = EXCLUDED.fiche_id,
                    source_file = EXCLUDED.source_file,
                    page_key = EXCLUDED.page_key,
                    chunk_type = EXCLUDED.chunk_type,
                    ordinal = EXCLUDED.ordinal,
                    content = EXCLUDED.content,
                    metadata = EXCLUDED.metadata
                """,
                (
                    chunk_row["chunk_id"],
                    chunk_row["fiche_id"],
                    chunk_row["source_file"],
                    chunk_row["page_key"],
                    chunk_row["chunk_type"],
                    chunk_row.get("ordinal", 0),
                    chunk_row["content"],
                    json.dumps(chunk_row.get("metadata") or {}),
                ),
            )

    def delete_orphan_chunks(
        self,
        connection: psycopg.Connection,
        fiche_ids: list[str],
        keep_chunk_ids: list[str],
    ) -> int:
        if not fiche_ids:
            return 0
        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM chunks WHERE fiche_id = ANY(%s) AND NOT (chunk_id = ANY(%s))",
                (fiche_ids, keep_chunk_ids),
            )
            return cursor.rowcount

    def delete_orphan_fiches(
        self,
        connection: psycopg.Connection,
        keep_fiche_ids: list[str],
    ) -> int:
        """Remove fiches (and their chunks, via ON DELETE CASCADE) that no longer
        appear in the current ingestion run -- e.g. a source page that was
        deduplicated away, renamed, or deleted from data/. Without this, a
        fiche_id dropped between two reindex runs lingers in Postgres forever,
        since upsert only ever adds/updates rows for the current fiche set."""
        with connection.cursor() as cursor:
            if not keep_fiche_ids:
                cursor.execute("DELETE FROM fiches")
            else:
                cursor.execute(
                    "DELETE FROM fiches WHERE NOT (fiche_id = ANY(%s))",
                    (keep_fiche_ids,),
                )
            return cursor.rowcount

    def upsert_conversation(
        self,
        connection: psycopg.Connection,
        *,
        conversation_key: str,
        user_id: int | None,
        role: str | None,
        channel: str,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO conversations (conversation_key, user_id, role, channel, metadata)
                VALUES (%s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (conversation_key) DO UPDATE SET
                    role = EXCLUDED.role,
                    channel = EXCLUDED.channel,
                    last_message_at = NOW(),
                    metadata = conversations.metadata || EXCLUDED.metadata
                RETURNING id
                """,
                (conversation_key, user_id, role, channel, json.dumps(metadata or {})),
            )
            row = cursor.fetchone()
        return int(row[0])

    def insert_message(
        self,
        connection: psycopg.Connection,
        *,
        conversation_id: int,
        sender: str,
        content: str,
        message_type: str = "text",
        transcript: str | None = None,
        audio_path: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO messages (
                    conversation_id, sender, message_type, content, transcript, audio_path, metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
                RETURNING id
                """,
                (
                    conversation_id,
                    sender,
                    message_type,
                    content,
                    transcript,
                    audio_path,
                    json.dumps(metadata or {}),
                ),
            )
            row = cursor.fetchone()
        return int(row[0])

    def fetch_conversation_id_by_key(self, conversation_key: str) -> int | None:
        with self.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id FROM conversations WHERE conversation_key = %s",
                    (conversation_key,),
                )
                row = cursor.fetchone()
        return int(row[0]) if row else None

    def fetch_conversations(
        self,
        *,
        limit: int = 100,
        channel: str | None = None,
        role: str | None = None,
        user_id: int | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if channel:
            clauses.append("channel = %s")
            params.append(channel)
        if role:
            clauses.append("role = %s")
            params.append(role)
        if user_id is not None:
            clauses.append("user_id = %s")
            params.append(user_id)

        sql = (
            "SELECT id, conversation_key, user_id, role, channel, status, "
            "started_at, last_message_at, metadata, metadata->>'title' AS title "
            "FROM conversations"
        )
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY last_message_at DESC LIMIT %s"
        params.append(max(limit, 1))

        with self.connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(sql, params)
                return cursor.fetchall()

    def fetch_messages(self, *, conversation_key: str, limit: int = 200) -> list[dict[str, Any]]:
        sql = """
            SELECT m.id, m.conversation_id, m.sender, m.message_type, m.content,
                   m.transcript, m.audio_path, m.metadata, m.created_at
            FROM messages m
            JOIN conversations c ON c.id = m.conversation_id
            WHERE c.conversation_key = %s
            ORDER BY m.created_at ASC, m.id ASC
            LIMIT %s
        """
        with self.connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(sql, (conversation_key, max(limit, 1)))
                return cursor.fetchall()

    def insert_discussion_history(self, connection: psycopg.Connection, payload: dict[str, Any]) -> int:
        columns = [column for column in _DISCUSSION_HISTORY_COLUMNS if column in payload]
        values: list[Any] = []
        for column in columns:
            value = payload.get(column)
            if column in _DISCUSSION_HISTORY_JSON_COLUMNS and value is not None:
                values.append(json.dumps(value))
            else:
                values.append(value)
        placeholders = ", ".join(
            "%s::jsonb" if column in _DISCUSSION_HISTORY_JSON_COLUMNS else "%s" for column in columns
        )
        sql = (
            f"INSERT INTO discussion_history ({', '.join(columns)}) "
            f"VALUES ({placeholders}) RETURNING history_id"
        )
        with connection.cursor() as cursor:
            cursor.execute(sql, values)
            row = cursor.fetchone()
        return int(row[0])

    def fetch_discussion_history(
        self,
        conversation_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM discussion_history"
        params: list[Any] = []
        if conversation_id:
            sql += " WHERE conversation_id = %s"
            params.append(conversation_id)
        sql += " ORDER BY created_at DESC LIMIT %s"
        params.append(max(limit, 1))
        with self.connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(sql, params)
                return cursor.fetchall()

    def fetch_review_queue(self, limit: int = 100, status: str | None = None) -> list[dict[str, Any]]:
        sql = """
            SELECT
                dh.history_id, dh.conversation_id, dh.created_at, dh.original_query, dh.answer,
                dh.route, dh.intent, dh.filters, dh.response_source, dh.model_output, dh.llm_error,
                dh.hits, dh.reasoning_signals, dh.reasoning_summary, dh.sav_admin_analysis, dh.admin_alert,
                COALESCE(rc.review_status, 'pending') AS review_status,
                rc.decision, rc.review_notes, rc.corrected_answer, rc.knowledge_action,
                rc.reviewed_by, rc.reviewed_at, rc.updated_at
            FROM discussion_history dh
            LEFT JOIN review_cases rc ON rc.history_id = dh.history_id
        """
        params: list[Any] = []
        if status and status.lower() != "all":
            sql += " WHERE COALESCE(rc.review_status, 'pending') = %s"
            params.append(status)
        sql += " ORDER BY dh.created_at DESC LIMIT %s"
        params.append(max(limit, 1))
        with self.connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(sql, params)
                return cursor.fetchall()

    def upsert_review_case(self, connection: psycopg.Connection, payload: dict[str, Any]) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO review_cases (
                    history_id, review_status, decision, review_notes,
                    corrected_answer, knowledge_action, reviewed_by, reviewed_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (history_id) DO UPDATE SET
                    review_status = EXCLUDED.review_status,
                    decision = EXCLUDED.decision,
                    review_notes = EXCLUDED.review_notes,
                    corrected_answer = EXCLUDED.corrected_answer,
                    knowledge_action = EXCLUDED.knowledge_action,
                    reviewed_by = EXCLUDED.reviewed_by,
                    reviewed_at = NOW(),
                    updated_at = NOW()
                """,
                (
                    payload["history_id"],
                    payload["review_status"],
                    payload.get("decision"),
                    payload.get("review_notes"),
                    payload.get("corrected_answer"),
                    payload.get("knowledge_action"),
                    payload.get("reviewed_by"),
                ),
            )

    def insert_memory(
        self,
        connection: psycopg.Connection,
        *,
        scope: str,
        memory_type: str,
        content: str,
        source_conversation_id: int | None,
        status: str,
        confidence: float,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO memories (
                    scope, memory_type, content, source_conversation_id, status, confidence, metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
                RETURNING id
                """,
                (scope, memory_type, content, source_conversation_id, status, confidence, json.dumps(metadata or {})),
            )
            row = cursor.fetchone()
        return int(row[0])

    def fetch_active_memories(self, limit: int = 200) -> list[dict[str, Any]]:
        sql = (
            "SELECT id, scope, memory_type, content, source_conversation_id, source_message_id, "
            "status, confidence, tags, metadata, created_at, updated_at "
            "FROM memories WHERE status <> 'REJECTED' ORDER BY created_at DESC LIMIT %s"
        )
        with self.connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(sql, (max(limit, 1),))
                return cursor.fetchall()

    def insert_user(
        self,
        connection: psycopg.Connection,
        *,
        username: str,
        password_hash: str,
        role: str,
        display_name: str | None = None,
        email: str | None = None,
    ) -> int:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO users (username, password_hash, role, display_name, email)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                """,
                (username, password_hash, role, display_name, email),
            )
            row = cursor.fetchone()
        return int(row[0])

    def fetch_user_by_username(self, username: str) -> dict[str, Any] | None:
        sql = (
            "SELECT id, username, password_hash, role, display_name, email, is_active, created_at "
            "FROM users WHERE username = %s"
        )
        with self.connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(sql, (username,))
                return cursor.fetchone()

    def healthcheck(self) -> dict[str, Any]:
        with self.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_database(), current_user")
                database_name, database_user = cursor.fetchone()
        return {
            "status": "ok",
            "database": database_name,
            "user": database_user,
        }
