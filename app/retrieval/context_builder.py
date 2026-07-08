from __future__ import annotations

from app.config import settings
from schemas.retrieval_schema import BuiltContext, RetrievalResult


def build_context(result: RetrievalResult, limit: int | None = None) -> BuiltContext:
    snippets = []
    for hit in _select_context_hits(result, limit or settings.context_limit):
        client = hit.metadata.get("client") or "unknown"
        maintenance_number = hit.metadata.get("maintenance_number") or "unknown"
        chunk_type = hit.metadata.get("chunk_type") or "chunk"
        snippets.append(
            f"[score={hit.score:.3f}] type={chunk_type} client={client} maintenance={maintenance_number}\n{hit.content}"
        )
    return BuiltContext(
        query=result.query,
        snippets=snippets,
        context_text="\n\n".join(snippets),
    )


def _select_context_hits(result: RetrievalResult, limit: int) -> list:
    if limit <= 0:
        return []

    specific_hits = []
    overview_hits = []
    for hit in result.hits:
        chunk_type = str(hit.metadata.get("chunk_type") or "").strip().lower()
        if chunk_type in {"diffuser", "issue", "recharge"}:
            specific_hits.append(hit)
        else:
            overview_hits.append(hit)

    selected = specific_hits[:limit]
    if len(selected) >= limit:
        return selected

    seen_overview_fiches: set[str] = set()
    for hit in overview_hits:
        if len(selected) >= limit:
            break
        if hit.fiche_id in seen_overview_fiches:
            continue
        selected.append(hit)
        seen_overview_fiches.add(hit.fiche_id)

    if len(selected) >= limit:
        return selected

    selected_ids = {hit.chunk_id for hit in selected}
    for hit in result.hits:
        if len(selected) >= limit:
            break
        if hit.chunk_id in selected_ids:
            continue
        selected.append(hit)
        selected_ids.add(hit.chunk_id)
    return selected
