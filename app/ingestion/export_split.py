from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

from app.config import settings
from app.ingestion.normalize import load_fiches_from_directory
from schemas.fiche_schema import FicheSchema


def export_split_maintenance(
    raw_data_dir: str | None = None,
    output_dir: str | Path | None = None,
) -> dict[str, int | str]:
    result = export_processed_fiches(raw_data_dir=raw_data_dir, output_dir=output_dir)
    return {
        "source_dir": result["source_dir"],
        "output_dir": str(Path(result["output_dir"]) / "maintenance"),
        "exported_files": result["exported_by_type"].get("client_maintenance_form", 0),
    }


def export_processed_fiches(
    raw_data_dir: str | None = None,
    output_dir: str | Path | None = None,
) -> dict[str, object]:
    source_dir = raw_data_dir or settings.raw_data_dir
    destination_root = Path(output_dir or settings.processed_data_dir)
    destination_root.mkdir(parents=True, exist_ok=True)

    fiches = load_fiches_from_directory(source_dir)
    exported_by_type: dict[str, int] = defaultdict(int)

    for fiche in fiches:
        destination = destination_root / _document_type_directory_name(fiche.document_type)
        destination.mkdir(parents=True, exist_ok=True)
        file_name = _build_output_filename(fiche)
        target_path = destination / file_name
        target_path.write_text(
            json.dumps(_serialize_processed_fiche(fiche), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        exported_by_type[fiche.document_type] += 1

    return {
        "source_dir": str(source_dir),
        "output_dir": str(destination_root),
        "exported_files": sum(exported_by_type.values()),
        "exported_by_type": dict(sorted(exported_by_type.items())),
    }


def _build_output_filename(fiche: FicheSchema) -> str:
    if fiche.document_type == "diffuser_catalog_entry":
        product_name = fiche.raw_payload.get("produit") or fiche.client or fiche.page_key
        return f"{_slugify(product_name)}.json"
    source_stem = Path(fiche.source_file).stem
    suffix = fiche.maintenance_number or fiche.page_key
    safe_source = _slugify(source_stem)
    safe_page = _slugify(fiche.page_key)
    safe_suffix = _slugify(suffix)
    return f"{safe_source}__{safe_page}__{safe_suffix}.json"


def _slugify(value: str) -> str:
    lowered = value.strip().lower()
    normalized = re.sub(r"[^a-z0-9]+", "_", lowered)
    collapsed = normalized.strip("_")
    return collapsed or "unknown"


def _document_type_directory_name(document_type: str) -> str:
    if document_type == "client_maintenance_form":
        return "maintenance"
    return _slugify(document_type)


def _serialize_processed_fiche(fiche: FicheSchema) -> dict[str, object]:
    if fiche.document_type == "knowledge_base_entry":
        return {
            "fiche_id": fiche.fiche_id,
            "source_file": fiche.source_file,
            "page_key": fiche.page_key,
            "document_type": fiche.document_type,
            "category": fiche.raw_payload.get("category"),
            "title": fiche.raw_payload.get("question"),
            "content": fiche.raw_payload.get("answer"),
            "metadata": {
                key: value
                for key, value in fiche.raw_payload.items()
                if key not in {"question", "answer", "category"}
            },
        }
    if fiche.document_type == "diffuser_catalog_entry":
        return {
            "fiche_id": fiche.fiche_id,
            "source_file": fiche.source_file,
            "page_key": fiche.page_key,
            "document_type": fiche.document_type,
            "produit": fiche.raw_payload.get("produit") or fiche.client,
            "couverture": fiche.raw_payload.get("couverture"),
            "ideal_pour": fiche.raw_payload.get("ideal_pour", []),
            "avantages": fiche.raw_payload.get("avantages", []),
            "service_recommande": fiche.raw_payload.get("service_recommande"),
            "argument_commercial": fiche.raw_payload.get("argument_commercial"),
        }
    return fiche.model_dump(mode="json")
