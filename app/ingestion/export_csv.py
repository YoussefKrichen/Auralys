from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

from app.config import settings
from app.ingestion.normalize import load_fiches_from_directory
from schemas.fiche_schema import FicheSchema


def export_processed_csvs(
    processed_data_dir: str | None = None,
    output_dir: str | Path | None = None,
) -> dict[str, object]:
    source_dir = Path(processed_data_dir or settings.processed_data_dir)
    destination_dir = Path(output_dir or "data/processed_csv")
    destination_dir.mkdir(parents=True, exist_ok=True)

    fiches = load_fiches_from_directory(source_dir)
    grouped: dict[str, list[FicheSchema]] = defaultdict(list)
    for fiche in fiches:
        grouped[fiche.document_type].append(fiche)

    exported_files: dict[str, int] = {}
    for document_type, document_fiches in sorted(grouped.items()):
        csv_path = destination_dir / f"{_document_type_file_name(document_type)}.csv"
        _write_csv(csv_path, document_fiches)
        exported_files[csv_path.name] = len(document_fiches)

    return {
        "source_dir": str(source_dir),
        "output_dir": str(destination_dir),
        "exported_csv_files": len(exported_files),
        "rows_by_file": exported_files,
    }


def _write_csv(output_path: Path, fiches: list[FicheSchema]) -> None:
    fieldnames = [
        "fiche_id",
        "source_file",
        "page_key",
        "source_image",
        "document_type",
        "client",
        "maintenance_number",
        "address",
        "service_date",
        "service_time",
        "technician_name",
        "sav_numbers",
        "service_types",
        "diffuser_controls",
        "recharge_entries",
        "issue",
        "recommendation",
        "satisfied_service",
        "parfum_bien_diffuse",
        "signature_text",
        "searchable_text",
        "raw_payload",
    ]
    with output_path.open("w", encoding="utf-8-sig", newline="") as file_handle:
        writer = csv.DictWriter(file_handle, fieldnames=fieldnames)
        writer.writeheader()
        for fiche in fiches:
            writer.writerow(_fiche_to_csv_row(fiche))


def _fiche_to_csv_row(fiche: FicheSchema) -> dict[str, str]:
    return {
        "fiche_id": fiche.fiche_id,
        "source_file": fiche.source_file,
        "page_key": fiche.page_key,
        "source_image": fiche.source_image or "",
        "document_type": fiche.document_type,
        "client": fiche.client or "",
        "maintenance_number": fiche.maintenance_number or "",
        "address": fiche.maintenance_details.address or "",
        "service_date": str(fiche.maintenance_details.service_date or ""),
        "service_time": str(fiche.maintenance_details.service_time or ""),
        "technician_name": fiche.maintenance_details.technician_name or "",
        "sav_numbers": " | ".join(fiche.maintenance_details.sav_numbers),
        "service_types": " | ".join(fiche.service_type.active_labels()),
        "diffuser_controls": " || ".join(
            control.compact_summary()
            for control in fiche.controle_diffuseur_recharge
            if control.compact_summary()
        ),
        "recharge_entries": " || ".join(
            recharge.compact_summary()
            for recharge in fiche.recharge_bouteille_effectuee
            if recharge.compact_summary()
        ),
        "issue": fiche.probleme_recommandation.probleme_rencontree_raw or "",
        "recommendation": fiche.probleme_recommandation.solution_proposee or "",
        "satisfied_service": _bool_to_text(fiche.enquete_satisfaction_client.satisfied_service),
        "parfum_bien_diffuse": _bool_to_text(fiche.enquete_satisfaction_client.parfum_bien_diffuse),
        "signature_text": fiche.signature_cachet.text or "",
        "searchable_text": fiche.searchable_text(),
        "raw_payload": json.dumps(fiche.raw_payload, ensure_ascii=False),
    }


def _bool_to_text(value: bool | None) -> str:
    if value is None:
        return ""
    return "true" if value else "false"


def _document_type_file_name(document_type: str) -> str:
    return document_type.strip().lower().replace(" ", "_")
