from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import docx as docx_lib

from app.ingestion.client_reference_matcher import match_client_reference
from app.ingestion.gold_overrides import get_gold_client_address
from schemas.fiche_schema import (
    BottleRecharge,
    CompanyInfo,
    DiffuserControl,
    FicheSchema,
    MaintenanceDetails,
    ProblemRecommendation,
    ServiceType,
    SignatureCachet,
    SatisfactionSurvey,
)


def maybe_fix_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    if "Ã" in text or "Â" in text:
        try:
            repaired = text.encode("latin1").decode("utf-8")
            return repaired.strip()
        except (UnicodeEncodeError, UnicodeDecodeError):
            return text
    return text


def normalize_scalar(value: Any) -> Any:
    if isinstance(value, str):
        return maybe_fix_text(value)
    if isinstance(value, list):
        return [normalize_scalar(item) for item in value]
    if isinstance(value, dict):
        return {key: normalize_scalar(item) for key, item in value.items()}
    return value


def parse_service_date(raw_value: str | None):
    if not raw_value:
        return None
    for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%d.%m.%y", "%d/%m/%y"):
        try:
            return datetime.strptime(raw_value, fmt).date()
        except ValueError:
            continue
    return None


def parse_service_time(raw_value: str | None):
    if not raw_value:
        return None
    cleaned = raw_value.upper().replace(" ", "").replace("H", ":").strip(":")
    if cleaned.count(":") == 0 and cleaned.isdigit() and len(cleaned) <= 2:
        cleaned = f"{cleaned}:00"
    for fmt in ("%H:%M", "%H"):
        try:
            return datetime.strptime(cleaned, fmt).time()
        except ValueError:
            continue
    return None


def build_fiche_id(source_file: Path, page_key: str, maintenance_number: str | None) -> str:
    if maintenance_number:
        return f"{source_file.stem}:{page_key}:{maintenance_number}"
    return f"{source_file.stem}:{page_key}"


def normalize_page(source_file: Path, page_key: str, payload: dict[str, Any]) -> FicheSchema:
    normalized = normalize_scalar(payload)
    maintenance_details = MaintenanceDetails(**normalized.get("maintenance_details", {}))
    reference_match = match_client_reference(maintenance_details.client, maintenance_details.address)
    if reference_match and reference_match.reference.client_name:
        maintenance_details.client = reference_match.reference.client_name
        raw_maintenance = normalized.get("maintenance_details")
        if isinstance(raw_maintenance, dict):
            raw_maintenance["client"] = reference_match.reference.client_name
    maintenance_details.service_date = parse_service_date(maintenance_details.date_raw)
    maintenance_details.service_time = parse_service_time(maintenance_details.time_raw)
    fiche_id = build_fiche_id(
        source_file=source_file,
        page_key=page_key,
        maintenance_number=maintenance_details.client_maintenance_number,
    )
    return FicheSchema(
        fiche_id=fiche_id,
        source_file=str(source_file),
        page_key=page_key,
        source_image=normalized.get("source_image"),
        document_type=normalized.get("document_type") or "client_maintenance_form",
        company_info=CompanyInfo(**normalized.get("company_info", {})),
        maintenance_details=maintenance_details,
        service_type=ServiceType(**normalized.get("service_type", {})),
        controle_diffuseur_recharge=[
            DiffuserControl(**item)
            for item in normalized.get("controle_diffuseur_recharge", [])
        ],
        recharge_bouteille_effectuee=[
            BottleRecharge(**item)
            for item in normalized.get("recharge_bouteille_effectuee", [])
        ],
        probleme_recommandation=ProblemRecommendation(
            **normalized.get("probleme_recommandation", {})
        ),
        enquete_satisfaction_client=SatisfactionSurvey(
            **normalized.get("enquete_satisfaction_client", {})
        ),
        signature_cachet=SignatureCachet(**normalized.get("signature_cachet", {})),
        raw_payload=normalized,
    )


def normalize_diffuser_catalog_entry(
    source_file: Path,
    page_key: str,
    payload: dict[str, Any],
) -> FicheSchema:
    normalized = normalize_scalar(payload)
    product_name = normalized.get("produit") or f"catalog_item_{page_key}"
    fiche_id = build_fiche_id(
        source_file=source_file,
        page_key=page_key,
        maintenance_number=None,
    )
    return FicheSchema(
        fiche_id=fiche_id,
        source_file=str(source_file),
        page_key=page_key,
        document_type="diffuser_catalog_entry",
        maintenance_details=MaintenanceDetails(client=product_name),
        controle_diffuseur_recharge=[
            DiffuserControl(
                model_diffuseur=product_name,
                emplacement="catalog",
                qualite_diffusion=normalized.get("couverture"),
            )
        ],
        probleme_recommandation=ProblemRecommendation(
            probleme_rencontree_raw=(
                "Ideal for: "
                + ", ".join(normalized.get("ideal_pour", []) or [])
            ),
            solution_proposee=(
                f"{normalized.get('service_recommande') or 'unknown service'}. "
                f"{normalized.get('argument_commercial') or ''}".strip()
            ),
        ),
        raw_payload=normalized,
    )


def normalize_knowledge_base_entry(
    source_file: Path,
    page_key: str,
    question: str,
    answer: str,
    *,
    category: str = "knowledge_base",
    metadata: dict[str, Any] | None = None,
) -> FicheSchema:
    normalized_question = maybe_fix_text(question) or question.strip()
    normalized_answer = maybe_fix_text(answer) or answer.strip()
    raw_payload = {
        "question": normalized_question,
        "answer": normalized_answer,
        "category": category,
        **(normalize_scalar(metadata or {}) or {}),
    }
    fiche_id = build_fiche_id(
        source_file=source_file,
        page_key=page_key,
        maintenance_number=None,
    )
    return FicheSchema(
        fiche_id=fiche_id,
        source_file=str(source_file),
        page_key=page_key,
        document_type="knowledge_base_entry",
        maintenance_details=MaintenanceDetails(client=f"knowledge:{category}"),
        probleme_recommandation=ProblemRecommendation(
            probleme_rencontree_raw=normalized_question,
            solution_proposee=normalized_answer,
        ),
        raw_payload=raw_payload,
    )


def _looks_like_maintenance_pages(payload: dict[str, Any]) -> bool:
    values = [value for value in payload.values() if isinstance(value, dict)]
    if not values:
        return False
    return any(
        any(key in value for key in ("maintenance_details", "service_type", "probleme_recommandation"))
        for value in values
    )


def _looks_like_normalized_fiche(payload: dict[str, Any]) -> bool:
    required_keys = {
        "fiche_id",
        "source_file",
        "page_key",
        "document_type",
        "maintenance_details",
    }
    return required_keys.issubset(payload.keys())


def _looks_like_clean_knowledge_entry(payload: dict[str, Any]) -> bool:
    required_keys = {
        "fiche_id",
        "source_file",
        "page_key",
        "document_type",
        "title",
        "content",
    }
    return payload.get("document_type") == "knowledge_base_entry" and required_keys.issubset(payload.keys())


def _looks_like_clean_diffuser_catalog_entry(payload: dict[str, Any]) -> bool:
    required_keys = {
        "fiche_id",
        "source_file",
        "page_key",
        "document_type",
        "produit",
    }
    return payload.get("document_type") == "diffuser_catalog_entry" and required_keys.issubset(payload.keys())


def _apply_gold_override(fiche: FicheSchema) -> None:
    """Overwrite client/address with the human-reviewed value from the
    client_address_gold layer (data/gold/), when this fiche has been through
    that review. Takes priority over the automatic fuzzy matcher below since
    it reflects a validated decision rather than a heuristic guess."""
    gold = get_gold_client_address(fiche.fiche_id)
    if not gold:
        return
    client_gold, address_gold = gold
    if client_gold:
        fiche.maintenance_details.client = client_gold
    if address_gold:
        fiche.maintenance_details.address = address_gold


def _load_normalized_fiche(source_file: Path, payload: dict[str, Any]) -> list[FicheSchema]:
    normalized = normalize_scalar(payload)
    fiche = FicheSchema(**normalized)
    if fiche.document_type == "client_maintenance_form":
        fiche.maintenance_details.service_date = parse_service_date(fiche.maintenance_details.date_raw)
        fiche.maintenance_details.service_time = parse_service_time(fiche.maintenance_details.time_raw)
        _apply_gold_override(fiche)
    fiche.source_file = str(Path(fiche.source_file))
    if not fiche.raw_payload:
        fiche.raw_payload = normalized.get("raw_payload", {})
    return [fiche]


def _load_clean_knowledge_entry(source_file: Path, payload: dict[str, Any]) -> list[FicheSchema]:
    metadata = payload.get("metadata")
    return [
        normalize_knowledge_base_entry(
            source_file=Path(payload.get("source_file") or source_file),
            page_key=str(payload.get("page_key") or "unknown"),
            question=str(payload.get("title") or ""),
            answer=str(payload.get("content") or ""),
            category=str(payload.get("category") or "knowledge_base"),
            metadata=metadata if isinstance(metadata, dict) else None,
        )
    ]


def _load_clean_diffuser_catalog_entry(source_file: Path, payload: dict[str, Any]) -> list[FicheSchema]:
    normalized_payload = {
        "produit": payload.get("produit"),
        "couverture": payload.get("couverture"),
        "ideal_pour": payload.get("ideal_pour") if isinstance(payload.get("ideal_pour"), list) else [],
        "avantages": payload.get("avantages") if isinstance(payload.get("avantages"), list) else [],
        "service_recommande": payload.get("service_recommande"),
        "argument_commercial": payload.get("argument_commercial"),
    }
    return [
        normalize_diffuser_catalog_entry(
            source_file=Path(payload.get("source_file") or source_file),
            page_key=str(payload.get("page_key") or "unknown"),
            payload=normalized_payload,
        )
    ]


def _looks_like_form_response_export(payload: dict[str, Any]) -> bool:
    responses = payload.get("Form Responses 1")
    return isinstance(responses, list)


def _load_form_response_export(source_file: Path, payload: dict[str, Any]) -> list[FicheSchema]:
    fiches: list[FicheSchema] = []
    responses = payload.get("Form Responses 1") or []
    for response_index, response in enumerate(responses, start=1):
        if not isinstance(response, dict):
            continue
        response_metadata = {
            "response_index": response_index,
            "timestamp": response.get("Timestamp"),
        }
        ordinal = 0
        for question, answer in response.items():
            if question == "Timestamp":
                continue
            normalized_answer = maybe_fix_text(str(answer)) if answer is not None else None
            if not normalized_answer:
                continue
            ordinal += 1
            fiches.append(
                normalize_knowledge_base_entry(
                    source_file=source_file,
                    page_key=f"response_{response_index}_question_{ordinal}",
                    question=str(question),
                    answer=normalized_answer,
                    category="survey_knowledge",
                    metadata=response_metadata,
                )
            )
    return fiches


def _load_docx_knowledge(source_file: Path) -> list[FicheSchema]:
    """Split a .docx report into one fiche per section, using the document's
    actual Heading 1/Heading 2 styles rather than guessing from raw text (the
    previous approach re-parsed document.xml and flagged a paragraph as a
    heading if it was all-uppercase or started with a digit -- fragile on any
    document that doesn't happen to follow that convention)."""
    document = docx_lib.Document(str(source_file))

    sections: list[tuple[str | None, str, list[str]]] = []
    current_h1: str | None = None
    current_title = "Introduction"
    current_lines: list[str] = []

    def flush() -> None:
        if current_lines:
            sections.append((current_h1, current_title, current_lines))

    for paragraph in document.paragraphs:
        text = (paragraph.text or "").strip()
        if not text:
            continue
        text = maybe_fix_text(text) or text
        style = paragraph.style.name if paragraph.style else ""
        if style == "Heading 1":
            flush()
            current_h1 = text
            current_title = text
            current_lines = []
        elif style == "Heading 2":
            flush()
            current_title = text
            current_lines = []
        else:
            current_lines.append(text)
    flush()

    fiches: list[FicheSchema] = []
    for index, (parent, title, lines) in enumerate(sections, start=1):
        answer = "\n".join(lines).strip()
        if not answer:
            continue
        fiches.append(
            normalize_knowledge_base_entry(
                source_file=source_file,
                page_key=f"section_{index}",
                question=title,
                answer=answer,
                category="docx_report",
                metadata={
                    "source_format": "docx",
                    "section_index": index,
                    "parent_section": parent if parent and parent != title else None,
                },
            )
        )
    return fiches


def load_fiches_from_file(file_path: str | Path) -> list[FicheSchema]:
    source_file = Path(file_path)
    if source_file.suffix.lower() == ".docx":
        return _load_docx_knowledge(source_file)
    if source_file.suffix.lower() == ".csv":
        from app.ingestion.csv_intervention_loader import EXPECTED_HEADER, load_fiches_from_csv

        with source_file.open("r", encoding="utf-8-sig", newline="") as handle:
            header = next(csv.reader(handle), [])
        if [cell.strip() for cell in header[: len(EXPECTED_HEADER)]] != EXPECTED_HEADER:
            # Not an intervention export (e.g. the client/address reference
            # registry) -- skip rather than misparse its columns positionally.
            raise ValueError(f"Unrecognized CSV header in {source_file}")
        return load_fiches_from_csv(source_file)

    payload = json.loads(source_file.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and _looks_like_normalized_fiche(payload):
        return _load_normalized_fiche(source_file, payload)
    if isinstance(payload, dict) and _looks_like_clean_knowledge_entry(payload):
        return _load_clean_knowledge_entry(source_file, payload)
    if isinstance(payload, dict) and _looks_like_clean_diffuser_catalog_entry(payload):
        return _load_clean_diffuser_catalog_entry(source_file, payload)
    if isinstance(payload, dict) and _looks_like_form_response_export(payload):
        return _load_form_response_export(source_file, payload)
    if isinstance(payload, dict) and _looks_like_maintenance_pages(payload):
        return [
            normalize_page(source_file=source_file, page_key=page_key, payload=page_payload)
            for page_key, page_payload in payload.items()
            if isinstance(page_payload, dict)
        ]
    if isinstance(payload, list):
        entries = [
            entry for entry in payload if isinstance(entry, dict) and "produit" in entry
        ]
        if not entries:
            raise ValueError(f"Unsupported JSON payload in {source_file}")
        return [
            normalize_diffuser_catalog_entry(
                source_file=source_file,
                page_key=str(index),
                payload=entry,
            )
            for index, entry in enumerate(entries, start=1)
        ]
    raise ValueError(f"Unsupported JSON payload in {source_file}")


def _dedupe_by_maintenance_number(fiches: list[FicheSchema]) -> list[FicheSchema]:
    """Some source pages were ingested twice under different batch folders
    (e.g. the same maintenance_number appears under both Aromair_01_06 and
    Aromair_03_01), producing byte-identical fiches/chunks that compete for
    the same rank at retrieval time. Keep the first occurrence only."""
    seen_numbers: set[str] = set()
    deduped: list[FicheSchema] = []
    for fiche in fiches:
        if fiche.document_type == "client_maintenance_form" and fiche.maintenance_number:
            if fiche.maintenance_number in seen_numbers:
                continue
            seen_numbers.add(fiche.maintenance_number)
        deduped.append(fiche)
    return deduped


def load_fiches_from_directory(directory: str | Path) -> list[FicheSchema]:
    data_dir = Path(directory)
    fiches: list[FicheSchema] = []
    candidates = (
        sorted(data_dir.rglob("*.json"))
        + sorted(data_dir.rglob("*.docx"))
        + sorted(data_dir.rglob("*.csv"))
    )
    for file_path in candidates:
        if file_path.name.startswith("~$") or file_path.name.startswith("."):
            continue  # editor lock/temp files (e.g. Word leaves ~$name.docx while open)
        try:
            fiches.extend(load_fiches_from_file(file_path))
        except ValueError:
            continue
    return _dedupe_by_maintenance_number(fiches)


def fiches_to_rows(fiches: Iterable[FicheSchema]) -> list[dict[str, Any]]:
    rows = []
    for fiche in fiches:
        rows.append(
            {
                "fiche_id": fiche.fiche_id,
                "source_file": fiche.source_file,
                "page_key": fiche.page_key,
                "client": fiche.client,
                "maintenance_number": fiche.maintenance_number,
                "service_date": fiche.maintenance_details.service_date,
                "service_time": fiche.maintenance_details.service_time,
                "service_types": fiche.service_type.active_labels(),
                "searchable_text": fiche.searchable_text(),
                "payload": fiche.model_dump(mode="json"),
            }
        )
    return rows
