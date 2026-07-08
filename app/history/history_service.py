from __future__ import annotations

import uuid
from typing import Any

from app.db import Database, default_database
from schemas.pipeline_schema import PipelineResponse


class HistoryService:
    def __init__(self, database: Database | None = None) -> None:
        self.database = database or default_database

    def ensure_schema(self) -> None:
        self.database.init_schema()

    def new_conversation_id(self) -> str:
        return str(uuid.uuid4())

    def save_response(
        self,
        response: PipelineResponse,
        conversation_id: str | None = None,
        user_id: int | None = None,
        role: str | None = None,
    ) -> tuple[int, str]:
        self.ensure_schema()
        resolved_conversation_id = conversation_id or response.conversation_id or self.new_conversation_id()
        payload = response.model_dump(mode="json")
        payload["conversation_id"] = resolved_conversation_id
        with self.database.connection() as connection:
            conversation_pk = self.database.upsert_conversation(
                connection,
                conversation_key=resolved_conversation_id,
                user_id=user_id,
                role=role,
                channel="voice" if response.input_type == "voice" else "chat",
                metadata={
                    "source": "question_pipeline",
                    "route": str(response.route),
                    "intent": response.intent,
                    "title": _build_conversation_title(
                        response.original_query if response.input_type == "text" else (response.transcript or response.original_query)
                    ),
                },
            )
            self.database.insert_message(
                connection,
                conversation_id=conversation_pk,
                sender="user",
                content=response.original_query if response.input_type == "text" else (response.transcript or response.original_query),
                message_type=response.input_type,
                transcript=response.transcript,
                audio_path=response.original_query if response.input_type == "voice" else None,
                metadata={
                    "normalized_query": response.normalized_query,
                    "filters": response.filters.model_dump(mode="json"),
                },
            )
            self.database.insert_message(
                connection,
                conversation_id=conversation_pk,
                sender="assistant",
                content=response.answer,
                message_type="text",
                metadata={
                    "response_source": response.response_source,
                    "intent": response.intent,
                    "route": str(response.route),
                    "hits": response.hits,
                },
            )
            history_id = self.database.insert_discussion_history(connection, payload)
        return history_id, resolved_conversation_id

    def list_history(
        self,
        conversation_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        self.ensure_schema()
        return self.database.fetch_discussion_history(conversation_id=conversation_id, limit=limit)

    def list_conversations(
        self,
        *,
        limit: int = 100,
        channel: str | None = None,
        role: str | None = None,
        user_id: int | None = None,
    ) -> list[dict[str, Any]]:
        self.ensure_schema()
        return self.database.fetch_conversations(limit=limit, channel=channel, role=role, user_id=user_id)

    def list_messages(
        self,
        *,
        conversation_key: str,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        self.ensure_schema()
        return self.database.fetch_messages(conversation_key=conversation_key, limit=limit)


def _build_conversation_title(text: str | None) -> str:
    raw = str(text or "").strip()
    for marker in ("Contexte image fourni:", "Image context provided:"):
        if marker in raw:
            raw = raw.split(marker, 1)[0].strip()
    normalized = " ".join(raw.split())
    if not normalized:
        return "Untitled"
    return normalized[:48].rstrip()
