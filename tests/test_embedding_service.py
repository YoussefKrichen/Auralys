from __future__ import annotations

from app.embeddings.embedding_service import EmbeddingService


def _dot(left: list[float], right: list[float]) -> float:
    return sum(l * r for l, r in zip(left, right))


def test_embedding_prefers_domain_related_text():
    service = EmbeddingService()
    query = service.embed_text("diffuseur fuite entree pharmacie")
    related = service.embed_text("Le diffuseur presente une fuite a l entree de la pharmacie")
    unrelated = service.embed_text("Catalogue marketing pour parfum ambiance premium")

    assert _dot(query, related) > _dot(query, unrelated)


def test_embedding_synonyms_help_related_matches():
    service = EmbeddingService()
    query = service.embed_text("depannage machine accueil")
    related = service.embed_text("maintenance diffuseur entree")
    unrelated = service.embed_text("recharge parfum bouteille")

    assert _dot(query, related) > _dot(query, unrelated)
