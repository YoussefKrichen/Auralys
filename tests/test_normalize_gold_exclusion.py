from __future__ import annotations

import json
import tempfile
from pathlib import Path

from app.ingestion.normalize import load_fiches_from_directory

_MAINTENANCE_PAGE = {
    "page_1": {
        "document_type": "client_maintenance_form",
        "maintenance_details": {
            "client": "Excluded Client",
            "client_maintenance_number": "999001",
            "date_raw": "06/01/26",
        },
        "service_type": {"visite": True},
        "controle_diffuseur_recharge": [],
        "recharge_bouteille_effectuee": [],
        "probleme_recommandation": {},
    }
}

_KNOWLEDGE_ENTRY = {
    "fiche_id": "kb:included:1",
    "source_file": "included.json",
    "page_key": "1",
    "document_type": "knowledge_base_entry",
    "title": "Comment nettoyer un diffuseur ?",
    "content": "Utiliser un chiffon sec, ne jamais utiliser de solvant.",
}


def _write_tree() -> Path:
    # tempfile directly, not pytest's tmp_path fixture -- see test_gold_data_source.py.
    root = Path(tempfile.mkdtemp())
    maintenance_dir = root / "Maintenance_json"
    maintenance_dir.mkdir()
    (maintenance_dir / "excluded.json").write_text(
        json.dumps(_MAINTENANCE_PAGE), encoding="utf-8"
    )
    knowledge_dir = root / "knowledge_base"
    knowledge_dir.mkdir()
    (knowledge_dir / "included.json").write_text(
        json.dumps(_KNOWLEDGE_ENTRY), encoding="utf-8"
    )
    return root


def test_load_fiches_from_directory_skips_maintenance_json_subdirectory():
    root = _write_tree()

    fiches = load_fiches_from_directory(root)

    clients = [fiche.client for fiche in fiches if fiche.document_type == "client_maintenance_form"]
    assert "Excluded Client" not in clients


def test_load_fiches_from_directory_still_loads_other_content():
    root = _write_tree()

    fiches = load_fiches_from_directory(root)

    document_types = {fiche.document_type for fiche in fiches}
    assert "knowledge_base_entry" in document_types
