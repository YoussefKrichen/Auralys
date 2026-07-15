from __future__ import annotations

import re
from typing import Any

from schemas.agent_schema import Citation

_LIST_KEYS = (
    "hits",
    "documents",
    "similar_cases",
    "history",
    "interventions",
    "reclamations",
    "ranked_destinations",
)
_MAX_SOURCES = 8


def extract_citable_sources(payload: dict[str, Any]) -> list[Citation]:
    """Scan a skill's payload for identifiable source records, regardless of
    which shape it uses -- RAG hits (hits/documents/similar_cases, identified
    via fiche_id/metadata) or operational records (history/interventions/
    reclamations/ranked_destinations, identified via maintenance_number/
    client_name from OperationsDataTool._fiche_to_intervention)."""
    sources: list[Citation] = []
    seen_keys: set[str] = set()
    for key in _LIST_KEYS:
        items = payload.get(key)
        if not isinstance(items, list):
            continue
        for item in items:
            if len(sources) >= _MAX_SOURCES:
                return sources
            if not isinstance(item, dict):
                continue
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            fiche_id = item.get("fiche_id") or metadata.get("fiche_id")
            maintenance_number = item.get("maintenance_number") or metadata.get("maintenance_number")
            if not (fiche_id or maintenance_number):
                continue
            dedupe_key = str(fiche_id or maintenance_number)
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)
            client = item.get("client") or item.get("client_name") or metadata.get("client")
            chunk_type = item.get("chunk_type") or metadata.get("chunk_type")
            sources.append(
                Citation(
                    index=len(sources) + 1,
                    fiche_id=fiche_id,
                    maintenance_number=maintenance_number,
                    client=client,
                    chunk_type=chunk_type,
                )
            )
    return sources


def build_sources_prompt_block(sources: list[Citation]) -> str:
    if not sources:
        return ""
    lines = [
        "Sources disponibles (cite leur numero entre crochets juste apres une "
        "affirmation qui s'appuie dessus, ex: ... [2]. Ne cite jamais un numero "
        "absent de cette liste, et n'ajoute aucun crochet si aucune source ne "
        "couvre l'affirmation) :"
    ]
    for source in sources:
        descriptor_parts = []
        if source.client:
            descriptor_parts.append(f"client {source.client}")
        if source.maintenance_number:
            descriptor_parts.append(f"fiche {source.maintenance_number}")
        if source.chunk_type:
            descriptor_parts.append(f"type {source.chunk_type}")
        descriptor = ", ".join(descriptor_parts) or (source.fiche_id or "source sans identifiant")
        lines.append(f"[{source.index}] {descriptor}")
    return "\n".join(lines)


def extract_cited_sources(answer_text: str, sources: list[Citation]) -> list[Citation]:
    """Only trust citation markers the model actually produced in its final
    answer -- guards against inventing sources that were merely offered."""
    if not sources or not answer_text:
        return []
    by_index = {source.index: source for source in sources}
    cited: list[Citation] = []
    seen_indices: set[int] = set()
    for match in re.finditer(r"\[(\d+)\]", answer_text):
        index = int(match.group(1))
        if index in seen_indices:
            continue
        source = by_index.get(index)
        if source is None:
            continue
        seen_indices.add(index)
        cited.append(source)
    return cited
