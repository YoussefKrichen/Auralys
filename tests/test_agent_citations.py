from __future__ import annotations

from app.llm.citations import build_sources_prompt_block, extract_cited_sources, extract_citable_sources
from schemas.agent_schema import Citation


def test_extract_citable_sources_from_rag_hits_dedupes_by_fiche_id():
    payload = {
        "hits": [
            {
                "chunk_id": "c1",
                "fiche_id": "f1",
                "score": 0.9,
                "content": "Diffuseur en panne",
                "source": "qdrant",
                "metadata": {"maintenance_number": "015602", "client": "Red Cattle"},
            },
            {
                "chunk_id": "c2",
                "fiche_id": "f1",
                "score": 0.8,
                "content": "Meme fiche, chunk different",
                "source": "qdrant",
                "metadata": {"maintenance_number": "015602", "client": "Red Cattle"},
            },
        ]
    }

    sources = extract_citable_sources(payload)

    assert len(sources) == 1
    assert sources[0].index == 1
    assert sources[0].client == "Red Cattle"
    assert sources[0].maintenance_number == "015602"


def test_extract_citable_sources_from_intervention_records():
    payload = {
        "history": [
            {
                "client_id": "pharmacie-victoria",
                "client_name": "Pharmacie Victoria",
                "maintenance_number": "099999",
                "issue": "fuite au niveau du diffuseur",
            }
        ]
    }

    sources = extract_citable_sources(payload)

    assert len(sources) == 1
    assert sources[0].client == "Pharmacie Victoria"
    assert sources[0].maintenance_number == "099999"


def test_extract_citable_sources_ignores_records_without_identifiers():
    payload = {"hits": [{"content": "Hit sans fiche_id ni maintenance_number"}]}

    assert extract_citable_sources(payload) == []


def test_extract_citable_sources_caps_at_eight():
    payload = {
        "hits": [
            {"fiche_id": f"f{i}", "metadata": {"client": f"Client {i}"}}
            for i in range(12)
        ]
    }

    sources = extract_citable_sources(payload)

    assert len(sources) == 8
    assert [source.index for source in sources] == list(range(1, 9))


def test_build_sources_prompt_block_lists_every_source():
    sources = [
        Citation(index=1, client="Red Cattle", maintenance_number="015602"),
        Citation(index=2, client="Pharmacie Victoria", maintenance_number="099999"),
    ]

    block = build_sources_prompt_block(sources)

    assert "[1] client Red Cattle, fiche 015602" in block
    assert "[2] client Pharmacie Victoria, fiche 099999" in block


def test_build_sources_prompt_block_empty_when_no_sources():
    assert build_sources_prompt_block([]) == ""


def test_extract_cited_sources_keeps_only_real_markers_in_order_of_first_appearance():
    sources = [
        Citation(index=1, client="A", maintenance_number="1"),
        Citation(index=2, client="B", maintenance_number="2"),
    ]
    answer = "Chez A tout va bien [1]. Un point invente [5], puis un rappel [1] et enfin [2]."

    cited = extract_cited_sources(answer, sources)

    assert [source.index for source in cited] == [1, 2]


def test_extract_cited_sources_empty_when_no_markers_or_no_sources():
    sources = [Citation(index=1, client="A")]

    assert extract_cited_sources("Reponse sans aucune citation.", sources) == []
    assert extract_cited_sources("Reponse avec [1].", []) == []
