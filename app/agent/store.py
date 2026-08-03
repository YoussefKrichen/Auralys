from __future__ import annotations

import json
import threading
import uuid
from typing import Any

from app.db import Database, default_database
from schemas.agent_schema import ProposedAction


AGENT_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS agent_feedback (
    id BIGSERIAL PRIMARY KEY,
    conversation_id BIGINT REFERENCES conversations(id) ON DELETE CASCADE,
    user_id BIGINT,
    rating VARCHAR(50),
    correction TEXT,
    should_remember BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS agent_actions (
    id BIGSERIAL PRIMARY KEY,
    conversation_id BIGINT REFERENCES conversations(id) ON DELETE CASCADE,
    action_type VARCHAR(100),
    status VARCHAR(50),
    input_json JSONB,
    output_json JSONB,
    requires_approval BOOLEAN DEFAULT FALSE,
    approved_by BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS agent_tool_logs (
    id BIGSERIAL PRIMARY KEY,
    tool_name VARCHAR(100),
    input_json JSONB,
    output_json JSONB,
    success BOOLEAN,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


class AgentStore:
    # Class-level (not instance-level) because bootstrap.py builds a fresh
    # AgentStore per tool/service rather than sharing a singleton, so an
    # instance flag wouldn't be seen across those instances. Mirrors
    # PostgresDatabase.init_schema()'s _schema_ready guard: CREATE TABLE IF
    # NOT EXISTS still takes an AccessExclusiveLock even when it's a no-op,
    # and ensure_schema() runs on nearly every AgentStore call, so leaving it
    # unguarded deadlocks under concurrent requests the same way.
    _agent_schema_ready = False
    _agent_schema_lock = threading.Lock()

    def __init__(self, database: Database | None = None) -> None:
        self.database = database or default_database

    def ensure_schema(self) -> None:
        self.database.init_schema()
        if AgentStore._agent_schema_ready:
            return
        with AgentStore._agent_schema_lock:
            if AgentStore._agent_schema_ready:
                return
            with self.database.connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(AGENT_SCHEMA_SQL)
            AgentStore._agent_schema_ready = True

    def save_conversation(
        self,
        *,
        user_id: int,
        role: str,
        message: str,
        answer: str,
        intent: str,
        conversation_key: str | None = None,
    ) -> tuple[int, str, int]:
        self.ensure_schema()
        resolved_conversation_key = conversation_key or f"agent:{user_id}:{role}:{uuid.uuid4()}"
        with self.database.connection() as connection:
            conversation_id = self.database.upsert_conversation(
                connection,
                conversation_key=resolved_conversation_key,
                user_id=user_id,
                role=role,
                channel="agent_chat",
                metadata={
                    "source": "agent_orchestrator",
                    "intent": intent,
                    "title": _build_conversation_title(message),
                },
            )
            # A discussion_history row is required so this turn can be reviewed/corrected
            # by the CEO (review_cases + the learning-layer memory bridge key off history_id).
            history_id = self.database.insert_discussion_history(
                connection,
                {
                    "conversation_id": resolved_conversation_key,
                    "input_type": "text",
                    "original_query": message,
                    "route": intent,
                    "intent": intent,
                    "answer": answer,
                    "response_source": "agent_orchestrator",
                },
            )
            self.database.insert_message(
                connection,
                conversation_id=conversation_id,
                sender="user",
                content=message,
                message_type="text",
                metadata={"intent": intent, "source": "agent_orchestrator"},
            )
            self.database.insert_message(
                connection,
                conversation_id=conversation_id,
                sender="assistant",
                content=answer,
                message_type="text",
                metadata={"intent": intent, "source": "agent_orchestrator"},
                history_id=history_id,
            )
        return conversation_id, resolved_conversation_key, history_id

    def resolve_conversation_id(self, conversation_key: str) -> int | None:
        self.ensure_schema()
        return self.database.fetch_conversation_id_by_key(conversation_key)

    def save_feedback(
        self,
        *,
        conversation_id: int,
        user_id: int | None,
        rating: str,
        correction: str | None,
        should_remember: bool,
    ) -> int:
        self.ensure_schema()
        with self.database.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO agent_feedback (
                        conversation_id,
                        user_id,
                        rating,
                        correction,
                        should_remember
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (conversation_id, user_id, rating, correction, should_remember),
                )
                row = cursor.fetchone()
        return int(row[0])


    def save_memory(
        self,
        *,
        memory_type: str,
        content: str,
        source: str | None,
        status: str = "PENDING",
        validated_by: int | None = None,
        importance: int = 1,
    ) -> int:
        self.ensure_schema()
        with self.database.connection() as connection:
            scope = "global"
            source_conversation_id = None
            metadata: dict[str, Any] = {
                "legacy_source": source,
                "importance": importance,
                "validated_by": validated_by,
            }
            if source and source.startswith("user:"):
                scope = source
            elif source and source.startswith("conversation:"):
                try:
                    source_conversation_id = int(source.split(":", 1)[1])
                except ValueError:
                    metadata["source_parse_error"] = source
            return self.database.insert_memory(
                connection,
                scope=scope,
                memory_type=memory_type,
                content=content,
                source_conversation_id=source_conversation_id,
                status=status,
                confidence=min(max(float(importance) / 5.0, 0.1), 1.0),
                metadata=metadata,
            )

    def get_active_memory(self) -> list[dict[str, Any]]:
        self.ensure_schema()
        rows = self.database.fetch_active_memories()
        normalized_rows: list[dict[str, Any]] = []
        for row in rows:
            metadata = row.get("metadata") or {}
            normalized_rows.append(
                {
                    "id": row["id"],
                    "memory_type": row["memory_type"],
                    "content": row["content"],
                    "source": metadata.get("legacy_source")
                    or (f"conversation:{row['source_conversation_id']}" if row.get("source_conversation_id") else None),
                    "scope": row["scope"],
                    "status": row["status"],
                    "validated_by": metadata.get("validated_by"),
                    "importance": metadata.get("importance"),
                    "topic": metadata.get("topic"),
                    "original_query": metadata.get("original_query"),
                    "confidence": row["confidence"],
                    "tags": row.get("tags") or [],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
            )
        return normalized_rows

    def get_active_business_rules(self, limit: int = 20) -> list[str]:
        relevant_types = {"BUSINESS_RULE", "KNOWLEDGE_CORRECTION"}
        rows = [
            row
            for row in self.get_active_memory()
            if row["status"] == "ACTIVE" and row["memory_type"].upper() in relevant_types
        ]
        return [row["content"] for row in rows[:limit]]

    def approve_memory(self, memory_id: int, *, reviewed_by: str | None = None) -> dict[str, Any] | None:
        self.ensure_schema()
        return self.database.set_memory_status(memory_id, status="ACTIVE", reviewed_by=reviewed_by)

    def reject_memory(self, memory_id: int, *, reviewed_by: str | None = None) -> dict[str, Any] | None:
        self.ensure_schema()
        return self.database.set_memory_status(memory_id, status="REJECTED", reviewed_by=reviewed_by)

    def get_user_preferences(self, user_id: int) -> dict[str, Any]:
        preferences: dict[str, Any] = {}
        for row in self.get_active_memory():
            if row["memory_type"].upper() != "USER_PREFERENCE":
                continue
            if not row["source"] or row["source"] != f"user:{user_id}":
                continue
            if ":" in row["content"]:
                key, value = row["content"].split(":", 1)
                preferences[key.strip()] = value.strip()
        return preferences

    def save_action(self, conversation_id: int, action: ProposedAction) -> int:
        self.ensure_schema()
        with self.database.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO agent_actions (
                        conversation_id,
                        action_type,
                        status,
                        input_json,
                        output_json,
                        requires_approval,
                        approved_by
                    )
                    VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
                    RETURNING id
                    """,
                    (
                        conversation_id,
                        action.action_type,
                        action.status.value,
                        json.dumps(action.input_json),
                        json.dumps(action.output_json),
                        action.requires_approval,
                        None,
                    ),
                )
                row = cursor.fetchone()
        return int(row[0])

    def list_pending_actions(self) -> list[dict[str, Any]]:
        self.ensure_schema()
        with self.database.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, conversation_id, action_type, status, input_json, output_json,
                           requires_approval, approved_by, created_at
                    FROM agent_actions
                    WHERE status = 'PENDING_APPROVAL'
                    ORDER BY created_at ASC, id ASC
                    """
                )
                rows = cursor.fetchall()
        return [self._row_to_action_dict(row) for row in rows]

    def get_action(self, action_id: int) -> dict[str, Any] | None:
        self.ensure_schema()
        with self.database.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, conversation_id, action_type, status, input_json, output_json,
                           requires_approval, approved_by, created_at
                    FROM agent_actions
                    WHERE id = %s
                    """,
                    (action_id,),
                )
                row = cursor.fetchone()
        return self._row_to_action_dict(row) if row is not None else None

    def update_action_status(
        self,
        *,
        action_id: int,
        status: str,
        approved_by: int | None,
        output_json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.ensure_schema()
        with self.database.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE agent_actions
                    SET status = %s,
                        approved_by = %s,
                        output_json = COALESCE(%s::jsonb, output_json)
                    WHERE id = %s
                    RETURNING id, conversation_id, action_type, status, input_json, output_json,
                              requires_approval, approved_by, created_at
                    """,
                    (
                        status,
                        approved_by,
                        json.dumps(output_json) if output_json is not None else None,
                        action_id,
                    ),
                )
                row = cursor.fetchone()
        if row is None:
            raise ValueError("Action not found.")
        return self._row_to_action_dict(row)

    def save_tool_log(
        self,
        *,
        tool_name: str,
        input_json: dict[str, Any],
        output_json: dict[str, Any] | None,
        success: bool,
        error_message: str | None = None,
    ) -> int:
        self.ensure_schema()
        with self.database.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO agent_tool_logs (
                        tool_name,
                        input_json,
                        output_json,
                        success,
                        error_message
                    )
                    VALUES (%s, %s::jsonb, %s::jsonb, %s, %s)
                    RETURNING id
                    """,
                    (
                        tool_name,
                        json.dumps(input_json),
                        json.dumps(output_json or {}),
                        success,
                        error_message,
                    ),
                )
                row = cursor.fetchone()
        return int(row[0])

    @staticmethod
    def _row_to_action_dict(row: Any) -> dict[str, Any]:
        return {
            "id": row[0],
            "conversation_id": row[1],
            "action_type": row[2],
            "status": row[3],
            "input_json": row[4] or {},
            "output_json": row[5] or {},
            "requires_approval": bool(row[6]),
            "approved_by": row[7],
            "created_at": row[8].isoformat() if row[8] is not None else None,
        }


def _build_conversation_title(text: str | None) -> str:
    raw = str(text or "").strip()
    for marker in ("Contexte image fourni:", "Image context provided:"):
        if marker in raw:
            raw = raw.split(marker, 1)[0].strip()
    normalized = " ".join(raw.split())
    if not normalized:
        return "Untitled"
    return normalized[:48].rstrip()
