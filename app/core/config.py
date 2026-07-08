from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv
from pydantic import BaseModel, Field


load_dotenv()


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Settings(BaseModel):
    app_name: str = "Auralys Backend"
    environment: str = "dev"
    api_prefix: str = "/api/auralys"
    host: str = "0.0.0.0"
    port: int = 8000
    postgres_dsn: str = "postgresql://auralys:auralys@localhost:5433/auralys"
    qdrant_url: str = "http://localhost:6333"
    qdrant_documents_collection: str = "auralys_documents"
    qdrant_memory_collection: str = "auralys_memory"
    embedding_dimension: int = 16
    qdrant_search_limit: int = 4
    auto_seed: bool = True
    log_level: str = "info"
    company_name: str = "Aromair"
    llm_backend: str = "mock"
    embedding_backend: str = "fake"
    human_validation_default: bool = True
    document_index_batch_size: int = 32
    default_priority: str = Field(default="medium")

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            app_name=os.getenv("AURALYS_APP_NAME", "Auralys Backend"),
            environment=os.getenv("AURALYS_ENV", "dev"),
            api_prefix=os.getenv("AURALYS_API_PREFIX", "/api/auralys"),
            host=os.getenv("AURALYS_HOST", "0.0.0.0"),
            port=int(os.getenv("AURALYS_PORT", "8000")),
            postgres_dsn=os.getenv(
                "POSTGRES_DSN",
                "postgresql://auralys:auralys@localhost:5433/auralys",
            ),
            qdrant_url=os.getenv("QDRANT_URL", "http://localhost:6333"),
            qdrant_documents_collection=os.getenv(
                "QDRANT_DOCUMENTS_COLLECTION",
                "auralys_documents",
            ),
            qdrant_memory_collection=os.getenv(
                "QDRANT_MEMORY_COLLECTION",
                "auralys_memory",
            ),
            embedding_dimension=int(os.getenv("EMBEDDING_DIMENSION", "16")),
            qdrant_search_limit=int(os.getenv("QDRANT_SEARCH_LIMIT", "4")),
            auto_seed=_as_bool(os.getenv("AURALYS_AUTO_SEED"), True),
            log_level=os.getenv("AURALYS_LOG_LEVEL", "info"),
            company_name=os.getenv("AURALYS_COMPANY_NAME", "Aromair"),
            llm_backend=os.getenv("AURALYS_LLM_BACKEND", "mock"),
            embedding_backend=os.getenv("AURALYS_EMBEDDING_BACKEND", "fake"),
            human_validation_default=_as_bool(
                os.getenv("AURALYS_HUMAN_VALIDATION_DEFAULT"),
                True,
            ),
            document_index_batch_size=int(
                os.getenv("AURALYS_DOCUMENT_INDEX_BATCH_SIZE", "32")
            ),
            default_priority=os.getenv("AURALYS_DEFAULT_PRIORITY", "medium"),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()
