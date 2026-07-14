from app.retrieval.context_builder import build_context
from schemas.retrieval_schema import RetrievalFilters, RetrievalHit
from app.retrieval.hybrid_retriever import HybridRetriever
from app.retrieval.query_router import route_query
from schemas.retrieval_schema import RetrievalResult, QueryIntent, RetrievalRoute


class _FakeSQLRetriever:
    def search(self, query, filters: RetrievalFilters, limit=None):
        return [
            RetrievalHit(
                chunk_id="c1",
                fiche_id="f1",
                score=1.0,
                content="Exact fiche match",
                source="sql",
                metadata={"client": "El Manana", "maintenance_number": "015500"},
            )
        ]


class _FakeQdrantRetriever:
    def search(self, query, filters: RetrievalFilters, limit=None):
        return [
            RetrievalHit(
                chunk_id="c2",
                fiche_id="f2",
                score=0.9,
                content="Semantic match",
                source="qdrant",
                metadata={"client": "Red Cattle", "maintenance_number": "015602"},
            )
        ]


def test_hybrid_retriever_merges_sources():
    retriever = HybridRetriever(_FakeSQLRetriever(), _FakeQdrantRetriever())
    result = retriever.search("fiche 015500")
    assert result.intent.value == "exact_lookup"
    assert len(result.hits) == 1
    assert result.hits[0].chunk_id == "c1"


def test_hybrid_retriever_uses_both_sources_for_client_semantic_query():
    retriever = HybridRetriever(_FakeSQLRetriever(), _FakeQdrantRetriever())
    result = retriever.search("Client: El Manana. Le diffuseur fuit a l'entree")
    assert result.intent == QueryIntent.mixed
    assert len(result.hits) == 2


def test_route_query_uses_hybrid_for_client_question_with_semantic_need():
    routed = route_query(
        "Client: Pharmacie Victoria. Le diffuseur fonctionne mal a l'entree, que faut-il verifier ?"
    )
    assert routed.intent == QueryIntent.mixed
    assert routed.route == RetrievalRoute.hybrid
    assert routed.filters.client == "Pharmacie Victoria"
    assert routed.filters.client_name == "Pharmacie Victoria"


def test_route_query_extracts_metadata_filters():
    routed = route_query(
        "Client: Pharmacie Victoria, source_file: data/raw_json/Aromair_01/Aromair_01_01.json, chunk_type: issue"
    )
    assert routed.filters.client_name == "Pharmacie Victoria"
    assert routed.filters.source_file == "data/raw_json/Aromair_01/Aromair_01_01.json"
    assert routed.filters.chunk_type == "issue"


def test_route_query_keeps_exact_client_lookup_postgres_only():
    routed = route_query("Client: Pharmacie Victoria")
    assert routed.intent == QueryIntent.client_lookup
    assert routed.route == RetrievalRoute.postgres


def test_context_builder_prefers_specific_chunks_before_overview():
    result = RetrievalResult(
        intent=QueryIntent.semantic,
        query="diffusion faible entree",
        filters=RetrievalFilters(),
        hits=[
            RetrievalHit(
                chunk_id="overview-1",
                fiche_id="fiche-1",
                score=0.95,
                content="Long overview",
                source="sql",
                metadata={"chunk_type": "overview", "client": "A"},
            ),
            RetrievalHit(
                chunk_id="diffuser-1",
                fiche_id="fiche-1",
                score=0.82,
                content="Diffuser issue at entrance",
                source="qdrant",
                metadata={"chunk_type": "diffuser", "client": "A"},
            ),
        ],
    )

    context = build_context(result, limit=1)
    assert len(context.snippets) == 1
    assert "type=diffuser" in context.snippets[0]
