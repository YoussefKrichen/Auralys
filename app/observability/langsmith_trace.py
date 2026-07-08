from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from app.config import settings


def _build_client() -> Any | None:
    if not settings.langsmith_tracing or not settings.langsmith_api_key:
        return None
    try:
        from langsmith import Client
    except ImportError:
        return None
    return Client(
        api_key=settings.langsmith_api_key,
        api_url=settings.langsmith_endpoint,
    )


def start_trace(name: str, inputs: dict[str, Any], metadata: dict[str, Any] | None = None) -> tuple[Any | None, str | None, dt.datetime]:
    client = _build_client()
    started_at = dt.datetime.now(dt.timezone.utc)
    if client is None:
        return None, None, started_at
    run_id = str(uuid.uuid4())
    try:
        client.create_run(
            name=name,
            run_type="chain",
            inputs=inputs,
            project_name=settings.langsmith_project,
            id=run_id,
            start_time=started_at,
            extra={"metadata": metadata or {}},
            tags=["auralys", "runtime", settings.llm_provider],
        )
    except Exception:
        return None, None, started_at
    return client, run_id, started_at


def finish_trace(
    client: Any | None,
    run_id: str | None,
    started_at: dt.datetime,
    outputs: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    if client is None or run_id is None:
        return
    try:
        client.update_run(
            run_id,
            end_time=dt.datetime.now(dt.timezone.utc),
            error=error,
            outputs=outputs,
            extra={"metadata": metadata or {}, "timing": {"start_time": started_at.isoformat()}},
        )
    except Exception:
        return
