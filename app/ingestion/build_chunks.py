from __future__ import annotations

from typing import Iterable
import re

from app.config import settings
from schemas.chunk_schema import ChunkSchema, ChunkType
from schemas.fiche_schema import FicheSchema, PROBLEM_CODE_LABELS, _is_plausible_diffuser_model


def _visit_date(fiche: FicheSchema) -> str:
    service_date = fiche.maintenance_details.service_date
    if service_date:
        return service_date.isoformat()
    return fiche.maintenance_details.date_raw or "date inconnue"


def _visit_context(fiche: FicheSchema) -> str:
    client = fiche.client or "client inconnu"
    maintenance_number = fiche.maintenance_number or "numero inconnu"
    return f"{client}, intervention {maintenance_number} du {_visit_date(fiche)}"


def _entity_context(fiche: FicheSchema) -> str:
    """Framing phrase for a diffuser/recharge/issue chunk, adapted to the document
    kind: only real maintenance visits have an intervention number/date to report."""
    if fiche.document_type == "client_maintenance_form":
        return f"chez {_visit_context(fiche)}"
    if fiche.document_type == "diffuser_catalog_entry":
        return f"pour {fiche.client or 'produit inconnu'}"
    return f"pour {fiche.client or 'source inconnue'}"


def _base_metadata(fiche: FicheSchema) -> dict:
    metadata = {
        "client": fiche.client,
        "client_name": fiche.client,
        "maintenance_number": fiche.maintenance_number,
        "service_types": fiche.service_type.active_labels(),
        "document_type": fiche.document_type,
        "service_date": fiche.maintenance_details.service_date.isoformat()
        if fiche.maintenance_details.service_date
        else None,
    }
    if fiche.document_type == "diffuser_catalog_entry":
        metadata.update(
            {
                "produit": fiche.raw_payload.get("produit"),
                "couverture": fiche.raw_payload.get("couverture"),
                "ideal_pour": fiche.raw_payload.get("ideal_pour", []),
                "avantages": fiche.raw_payload.get("avantages", []),
                "service_recommande": fiche.raw_payload.get("service_recommande"),
                "argument_commercial": fiche.raw_payload.get("argument_commercial"),
            }
        )
    if fiche.document_type == "knowledge_base_entry":
        metadata.update(
            {
                "knowledge_category": fiche.raw_payload.get("category"),
                "question": fiche.raw_payload.get("question"),
                "parent_section": fiche.raw_payload.get("parent_section"),
            }
        )
    return metadata


def build_chunks_for_fiche(fiche: FicheSchema) -> list[ChunkSchema]:
    chunks: list[ChunkSchema] = []
    base_metadata = _base_metadata(fiche)
    for index, content in enumerate(_split_text_by_token_budget(fiche.searchable_text()), start=0):
        chunks.append(
            ChunkSchema(
                chunk_id=f"{fiche.fiche_id}:overview:{index}",
                fiche_id=fiche.fiche_id,
                source_file=fiche.source_file,
                page_key=fiche.page_key,
                chunk_type=ChunkType.overview,
                ordinal=index,
                content=content,
                metadata=base_metadata,
            )
        )
    for index, diffuser in enumerate(fiche.controle_diffuseur_recharge, start=1):
        summary = diffuser.compact_summary()
        if not summary:
            continue
        chunks.append(
            ChunkSchema(
                chunk_id=f"{fiche.fiche_id}:diffuser:{index}",
                fiche_id=fiche.fiche_id,
                source_file=fiche.source_file,
                page_key=fiche.page_key,
                chunk_type=ChunkType.diffuser,
                ordinal=index,
                content=f"Diffuseur {index} {_entity_context(fiche)} : {summary}.",
                metadata={
                    **base_metadata,
                    "emplacement": diffuser.emplacement,
                    "model_diffuseur": diffuser.model_diffuseur,
                    "model_diffuseur_suspect": bool(
                        (diffuser.model_diffuseur or diffuser.model_diffuseur_raw)
                        and not _is_plausible_diffuser_model(
                            diffuser.model_diffuseur or diffuser.model_diffuseur_raw
                        )
                    ),
                    "reference_diffuseur": diffuser.reference_diffuseur,
                    "nom_parfum": diffuser.nom_parfum,
                    "qte_parfum_existante": diffuser.qte_parfum_existante,
                    "qualite_diffusion": diffuser.qualite_diffusion,
                    "fuite": diffuser.fuite,
                    "en_marche_arret": diffuser.en_marche_arret,
                },
            )
        )
    for index, recharge in enumerate(fiche.recharge_bouteille_effectuee, start=1):
        summary = recharge.compact_summary()
        if not summary:
            continue
        chunks.append(
            ChunkSchema(
                chunk_id=f"{fiche.fiche_id}:recharge:{index}",
                fiche_id=fiche.fiche_id,
                source_file=fiche.source_file,
                page_key=fiche.page_key,
                chunk_type=ChunkType.recharge,
                ordinal=index,
                content=f"Recharge {index} {_entity_context(fiche)} : {summary}.",
                metadata={
                    **base_metadata,
                    "emplacement": recharge.emplacement,
                    "parfum": recharge.parfum,
                    "ml": recharge.ml,
                    "frequence_diffusion": recharge.frequence_diffusion,
                    "plage_horaire_fonctionnement": recharge.plage_horaire_fonctionnement,
                },
            )
        )
    issue = fiche.probleme_recommandation.probleme_rencontree_raw
    solution = fiche.probleme_recommandation.solution_proposee
    problem_code = fiche.probleme_recommandation.probleme_rencontree_code
    if issue or solution:
        if fiche.document_type == "client_maintenance_form":
            content = f"Intervention chez {_visit_context(fiche)}."
            motif_label = PROBLEM_CODE_LABELS.get((problem_code or "").strip().upper())
            if motif_label:
                content += f" Motif : {motif_label}."
            content += f" Probleme signale : {issue or 'aucun'}."
            if solution:
                content += f" Solution proposee : {solution}."
        elif fiche.document_type == "knowledge_base_entry":
            content = f"Question : {issue or 'inconnue'}."
            if solution:
                content += f" Reponse : {solution}."
        else:
            content = f"Fiche produit {fiche.client or 'produit inconnu'}."
            content += f" Details : {issue or 'aucun'}."
            if solution:
                content += f" Recommandation : {solution}."
        chunks.append(
            ChunkSchema(
                chunk_id=f"{fiche.fiche_id}:issue:0",
                fiche_id=fiche.fiche_id,
                source_file=fiche.source_file,
                page_key=fiche.page_key,
                chunk_type=ChunkType.issue,
                ordinal=0,
                content=content,
                metadata={
                    **base_metadata,
                    "problem_code": problem_code,
                    "issue": issue,
                    "solution": solution,
                },
            )
        )
    return chunks


def build_chunks(fiches: Iterable[FicheSchema]) -> list[ChunkSchema]:
    chunks: list[ChunkSchema] = []
    for fiche in fiches:
        chunks.extend(build_chunks_for_fiche(fiche))
    return chunks


def _split_text_by_token_budget(text: str, target_tokens: int | None = None) -> list[str]:
    normalized = str(text or "").strip()
    if not normalized:
        return []

    budget = max(target_tokens or settings.chunk_target_tokens, 50)
    paragraphs = [part.strip() for part in normalized.splitlines() if part.strip()]
    segments: list[str] = []
    current_lines: list[str] = []
    current_tokens = 0

    for paragraph in paragraphs:
        paragraph_tokens = _estimate_token_count(paragraph)
        if paragraph_tokens > budget:
            if current_lines:
                segments.append("\n".join(current_lines))
                current_lines = []
                current_tokens = 0
            for sentence_chunk in _split_large_paragraph(paragraph, budget):
                segments.append(sentence_chunk)
            continue
        if current_lines and current_tokens + paragraph_tokens > budget:
            segments.append("\n".join(current_lines))
            current_lines = [paragraph]
            current_tokens = paragraph_tokens
            continue
        current_lines.append(paragraph)
        current_tokens += paragraph_tokens

    if current_lines:
        segments.append("\n".join(current_lines))
    return segments or [normalized]


def _split_large_paragraph(paragraph: str, budget: int) -> list[str]:
    sentence_candidates = re.split(r"(?<=[.!?])\s+", paragraph)
    parts = [part.strip() for part in sentence_candidates if part.strip()]
    if len(parts) <= 1:
        tokens = paragraph.split()
        return [
            " ".join(tokens[index : index + budget])
            for index in range(0, len(tokens), budget)
        ] or [paragraph]

    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0
    for part in parts:
        part_tokens = _estimate_token_count(part)
        if current and current_tokens + part_tokens > budget:
            chunks.append(" ".join(current))
            current = [part]
            current_tokens = part_tokens
            continue
        current.append(part)
        current_tokens += part_tokens
    if current:
        chunks.append(" ".join(current))
    return chunks


def _estimate_token_count(text: str) -> int:
    return max(len(re.findall(r"\S+", text)), 1)
