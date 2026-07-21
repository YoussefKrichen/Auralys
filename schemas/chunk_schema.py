from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ChunkType(str, Enum):
    overview = "overview"
    diffuser = "diffuser"
    recharge = "recharge"
    issue = "issue"
    information = "information"
    action = "action"


class ChunkSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")

    chunk_id: str
    fiche_id: str
    source_file: str
    page_key: str
    chunk_type: ChunkType
    ordinal: int = 0
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    def qdrant_payload(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "fiche_id": self.fiche_id,
            "source_file": self.source_file,
            "page_key": self.page_key,
            "chunk_type": self.chunk_type.value,
            "ordinal": self.ordinal,
            "content": self.content,
            **self.metadata,
        }
