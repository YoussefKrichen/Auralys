from __future__ import annotations

from collections import Counter
import hashlib
import math
import re
import unicodedata
from typing import Literal

from app.config import settings


EmbeddingTaskType = Literal["RETRIEVAL_QUERY", "RETRIEVAL_DOCUMENT", "SEMANTIC_SIMILARITY"]

EMBEDDING_STOPWORDS = {
    "a",
    "ai",
    "alors",
    "au",
    "aucun",
    "aussi",
    "aux",
    "avec",
    "ce",
    "ces",
    "cet",
    "cette",
    "comment",
    "dans",
    "de",
    "des",
    "du",
    "elle",
    "est",
    "et",
    "il",
    "je",
    "la",
    "le",
    "les",
    "leur",
    "leurs",
    "ma",
    "mais",
    "mes",
    "mon",
    "ne",
    "nos",
    "notre",
    "nous",
    "ou",
    "par",
    "pas",
    "plus",
    "pour",
    "que",
    "quel",
    "quelle",
    "quelles",
    "quels",
    "qui",
    "sa",
    "se",
    "ses",
    "son",
    "sur",
    "ta",
    "te",
    "tes",
    "ton",
    "tu",
    "un",
    "une",
    "vos",
    "votre",
    "vous",
}

SYNONYM_GROUPS = {
    "diffuseur": ("diffuseur", "diffusion", "diffuser", "machine"),
    "fuite": ("fuite", "fuit", "fuir", "leak"),
    "entree": ("entree", "accueil", "porte"),
    "parfum": ("parfum", "fragrance", "senteur"),
    "recharge": ("recharge", "bouteille", "bidon", "remplissage"),
    "pompe": ("pompe", "pression"),
    "maintenance": ("maintenance", "sav", "intervention", "depannage"),
    "pharmacie": ("pharmacie", "officine"),
    "client": ("client", "site", "magasin", "pointvente"),
    "probleme": ("probleme", "panne", "incident", "issue"),
    "solution": ("solution", "resolution", "reparation"),
}

TOKEN_TO_CANONICAL = {
    alias: canonical
    for canonical, aliases in SYNONYM_GROUPS.items()
    for alias in aliases
}


class EmbeddingService:
    def __init__(
        self,
        *,
        backend: str | None = None,
        model_name: str | None = None,
        dimension: int | None = None,
        allow_fallback: bool = True,
    ) -> None:
        self.dimension = dimension or settings.embedding_dimension
        self.backend = (backend or settings.embedding_backend).strip().lower()
        self.model_name = model_name or settings.embedding_model_name
        self.allow_fallback = allow_fallback
        self._gemini_client = None
        self._gemini_disabled = False

    def embed_text(
        self,
        text: str,
        *,
        task_type: EmbeddingTaskType = "SEMANTIC_SIMILARITY",
    ) -> list[float]:
        if self.backend == "gemini":
            vector = self._embed_with_gemini(text, task_type=task_type)
            if vector is not None:
                return vector
            if not self.allow_fallback:
                raise RuntimeError(
                    "Gemini embeddings are required for this phase, but the Gemini embedder is unavailable."
                )
        return self._local_embedding(text)

    def embed_texts(
        self,
        texts: list[str],
        *,
        task_type: EmbeddingTaskType = "SEMANTIC_SIMILARITY",
    ) -> list[list[float]]:
        return [self.embed_text(text, task_type=task_type) for text in texts]

    def _embed_with_gemini(
        self,
        text: str,
        *,
        task_type: EmbeddingTaskType,
    ) -> list[float] | None:
        if self._gemini_disabled:
            return None
        if not settings.google_api_key:
            if self.allow_fallback:
                return None
            raise RuntimeError(
                "Gemini embeddings require `GOOGLE_API_KEY` or `GEMINI_API_KEY` to be configured."
            )

        try:
            client = self._load_gemini_client()
            if client is None:
                if self.allow_fallback:
                    return None
                raise RuntimeError("Gemini embedding client could not be initialized.")
            from google.genai import types

            response = client.models.embed_content(
                model=self.model_name,
                contents=text,
                config=types.EmbedContentConfig(
                    taskType=task_type,
                    outputDimensionality=self.dimension,
                ),
            )
        except Exception as exc:
            self._gemini_disabled = True
            if not self.allow_fallback:
                raise RuntimeError("Gemini embedding request failed.") from exc
            return None

        embedding = getattr(response, "embeddings", None) or []
        if not embedding:
            return None

        values = getattr(embedding[0], "values", None) or []
        if not values:
            return None
        return _normalize_vector([float(value) for value in values])

    def _load_gemini_client(self):
        if self._gemini_client is not None:
            return self._gemini_client

        try:
            from google import genai
        except ImportError as exc:
            self._gemini_disabled = True
            if not self.allow_fallback:
                raise RuntimeError(
                    "Gemini embeddings require the `google-genai` package to be installed."
                ) from exc
            return None

        self._gemini_client = genai.Client(api_key=settings.google_api_key)
        return self._gemini_client

    def _local_embedding(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for feature, weight in _extract_weighted_features(text):
            digest = hashlib.sha256(feature.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign * weight
        return _normalize_vector(vector)


def _extract_weighted_features(text: str) -> list[tuple[str, float]]:
    normalized_text = _normalize_text(text)
    tokens = _tokenize(normalized_text)
    if not tokens:
        return []

    kept_tokens = [token for token in tokens if token not in EMBEDDING_STOPWORDS]
    if not kept_tokens:
        kept_tokens = tokens

    counts = Counter(kept_tokens)
    features: list[tuple[str, float]] = []

    for token, count in counts.items():
        tf_weight = 1.0 + math.log1p(count)
        features.append((f"tok:{token}", 3.2 * tf_weight))

        canonical = TOKEN_TO_CANONICAL.get(token)
        if canonical:
            features.append((f"syn:{canonical}", 2.4 * tf_weight))

        if token.isdigit():
            features.append((f"num:{token}", 4.5 * tf_weight))

        root = _light_stem(token)
        if root != token and len(root) >= 3:
            features.append((f"stem:{root}", 1.7 * tf_weight))

        for ngram in _char_ngrams(token, min_n=3, max_n=5):
            features.append((f"chr:{ngram}", 0.55 * tf_weight))

    for left, right in zip(kept_tokens, kept_tokens[1:]):
        features.append((f"bigram:{left}_{right}", 1.8))

    for first, second, third in zip(kept_tokens, kept_tokens[1:], kept_tokens[2:]):
        features.append((f"trigram:{first}_{second}_{third}", 1.2))

    return features


def _normalize_vector(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def _normalize_text(text: str) -> str:
    lowered = text.lower()
    ascii_text = unicodedata.normalize("NFKD", lowered).encode("ascii", "ignore").decode("ascii")
    ascii_text = ascii_text.replace("'", " ")
    ascii_text = re.sub(r"[^a-z0-9]+", " ", ascii_text)
    return re.sub(r"\s+", " ", ascii_text).strip()


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]{2,}", text)


def _char_ngrams(token: str, min_n: int, max_n: int) -> list[str]:
    padded = f"^{token}$"
    grams: list[str] = []
    for size in range(min_n, max_n + 1):
        if len(padded) < size:
            continue
        for index in range(len(padded) - size + 1):
            grams.append(padded[index : index + size])
    return grams


def _light_stem(token: str) -> str:
    suffixes = (
        "ations",
        "ation",
        "ements",
        "ement",
        "euses",
        "euse",
        "eaux",
        "aux",
        "ees",
        "ee",
        "ent",
        "ant",
        "ez",
        "er",
        "es",
        "e",
        "s",
    )
    for suffix in suffixes:
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            return token[: -len(suffix)]
    return token
