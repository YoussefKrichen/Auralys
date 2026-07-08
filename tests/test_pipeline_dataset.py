from __future__ import annotations

import json
import shutil
from pathlib import Path
from uuid import uuid4

from app.ingestion.build_chunks import build_chunks, build_chunks_for_fiche
from app.ingestion.client_reference_matcher import ClientReference, ClientReferenceMatch
from app.ingestion.export_unique_values import collect_unique_values
from app.ingestion.normalize import load_fiches_from_directory, load_fiches_from_file
from app.retrieval.hybrid_retriever import HybridRetriever
from app.retrieval.local_retriever import LocalRetriever
from schemas.chunk_schema import ChunkType
from schemas.retrieval_schema import RetrievalFilters


FIXTURE_DIR = Path("data/test_fixtures/pipeline")
TEST_WORK_DIR = Path(".test-work")


def _make_test_dir(name: str) -> Path:
    root = TEST_WORK_DIR / f"{name}-{uuid4().hex}"
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_load_maintenance_pages_parses_dates_times_and_quantities():
    fiches = load_fiches_from_file(FIXTURE_DIR / "maintenance_pages.json")

    assert len(fiches) == 2

    primary = fiches[0]
    assert primary.client == "716 Menzah6"
    assert primary.maintenance_number == "014972"
    assert primary.maintenance_details.service_date.isoformat() == "2025-02-10"
    assert primary.maintenance_details.service_time.isoformat() == "12:50:00"
    assert primary.controle_diffuseur_recharge[0].qte_parfum_existante == 97
    assert primary.recharge_bouteille_effectuee[0].ml == 300


def test_load_fixture_directory_supports_multiple_document_kinds():
    fiches = load_fiches_from_directory(FIXTURE_DIR)
    document_types = {fiche.document_type for fiche in fiches}
    clients = {fiche.client for fiche in fiches}

    assert "client_maintenance_form" in document_types
    assert "knowledge_base_entry" in document_types
    assert "diffuser_catalog_entry" in document_types
    assert "knowledge:survey_knowledge" in clients


def test_load_maintenance_pages_applies_fuzzy_client_reference_match(monkeypatch):
    fixture_payload = {
        "page_1": {
            "document_type": "client_maintenance_form",
            "maintenance_details": {
                "client": "719",
                "address": "Millenium Marsa",
                "client_maintenance_number": "015000",
            },
        }
    }
    root = _make_test_dir("fuzzy-client")
    try:
        fixture_file = root / "fuzzy_client.json"
        fixture_file.write_text(json.dumps(fixture_payload), encoding="utf-8")
        monkeypatch.setattr(
            "app.ingestion.normalize.match_client_reference",
            lambda client, address: ClientReferenceMatch(
                reference=ClientReference(client_name="716 Menzah6", address="Millenium Marsa"),
                score=0.67,
                client_score=0.62,
                address_score=0.8,
            ),
        )

        fiche = load_fiches_from_file(fixture_file)[0]

        assert fiche.client == "716 Menzah6"
        assert fiche.raw_payload["maintenance_details"]["client"] == "716 Menzah6"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_build_chunks_for_maintenance_contains_actionable_chunk_types():
    fiche = load_fiches_from_file(FIXTURE_DIR / "maintenance_pages.json")[0]
    chunks = build_chunks_for_fiche(fiche)
    chunk_types = [chunk.chunk_type for chunk in chunks]

    assert chunk_types == [
        ChunkType.overview,
        ChunkType.diffuser,
        ChunkType.recharge,
        ChunkType.issue,
    ]
    assert chunks[1].metadata["client"] == "716 Menzah6"
    assert chunks[1].metadata["client_name"] == "716 Menzah6"
    assert chunks[1].metadata["emplacement"] == "ENTREE"
    assert "Diffusion faible" in chunks[3].content


def test_build_chunks_splits_large_overview_text_around_token_budget(monkeypatch):
    fiche = load_fiches_from_file(FIXTURE_DIR / "maintenance_pages.json")[0]
    long_text = " ".join(f"token{i}" for i in range(1300))
    monkeypatch.setattr(type(fiche), "searchable_text", lambda self: long_text)

    chunks = build_chunks_for_fiche(fiche)
    overview_chunks = [chunk for chunk in chunks if chunk.chunk_type == ChunkType.overview]

    assert len(overview_chunks) >= 3
    assert all(len(chunk.content.split()) <= 600 for chunk in overview_chunks)


def test_collect_unique_values_from_fixture_directory_is_stable():
    payload = collect_unique_values(processed_data_dir=str(FIXTURE_DIR))

    assert payload["counts"] == {
        "clients": 2,
        "addresses": 2,
        "emplacements": 3,
    }
    assert "716 Menzah6" in payload["clients"]
    assert "Pharmacie Victoria" in payload["clients"]
    assert "ENTREE" in payload["emplacements"]


def test_collect_unique_values_title_cases_multi_word_client_names():
    fixture_payload = {
        "page_1": {
            "document_type": "client_maintenance_form",
            "maintenance_details": {
                "client": "aBi mEYDITH",
                "address": "Centre Urbain Nord",
            },
        },
        "page_2": {
            "document_type": "client_maintenance_form",
            "maintenance_details": {
                "client": "bOUTIQUA souKRA",
                "address": "La Soukra",
            },
        },
    }
    root = _make_test_dir("unique-values")
    try:
        fixture_file = root / "mixed_case_clients.json"
        fixture_file.write_text(json.dumps(fixture_payload), encoding="utf-8")

        payload = collect_unique_values(processed_data_dir=str(root))

        assert "Abi Meydith" in payload["clients"]
        assert "Boutiqua Soukra" in payload["clients"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_local_retriever_returns_specific_hits_from_fixture_chunks(monkeypatch):
    fixture_chunks = tuple(build_chunks(load_fiches_from_directory(FIXTURE_DIR)))
    monkeypatch.setattr(
        "app.retrieval.local_retriever._load_cached_chunks",
        lambda: fixture_chunks,
    )
    retriever = LocalRetriever()

    hits = retriever.search(
        "Client: 716 Menzah6. Diffusion faible entree pompe",
        RetrievalFilters(client="716 Menzah6"),
        limit=5,
    )

    assert hits
    assert hits[0].metadata["client"] == "716 Menzah6"
    assert hits[0].metadata["chunk_type"] in {"diffuser", "issue", "recharge"}


def test_hybrid_retriever_falls_back_to_local_fixture_data(monkeypatch):
    fixture_chunks = tuple(build_chunks(load_fiches_from_directory(FIXTURE_DIR)))
    monkeypatch.setattr(
        "app.retrieval.local_retriever._load_cached_chunks",
        lambda: fixture_chunks,
    )

    class _EmptySQLRetriever:
        def search(self, query, filters, limit=None):
            return []

    class _EmptyQdrantRetriever:
        def search(self, query, filters, limit=None):
            return []

    result = HybridRetriever(
        sql_retriever=_EmptySQLRetriever(),
        qdrant_retriever=_EmptyQdrantRetriever(),
        local_retriever=LocalRetriever(),
    ).search("Client: Pharmacie Victoria. Le diffuseur ne fonctionne plus a l'accueil")

    assert result.hits
    assert result.hits[0].metadata["retriever"] == "local"
    assert any(hit.metadata.get("client") == "Pharmacie Victoria" for hit in result.hits)
