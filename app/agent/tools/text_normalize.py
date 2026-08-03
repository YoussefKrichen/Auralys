from __future__ import annotations

import re
import unicodedata


def normalize_text(value: str) -> str:
    """Lowercase, strip accents, and collapse whitespace.

    Shared by emplacement canonicalization and client-name canonicalization --
    both need to treat "Entree"/"Entrée" or "Asteel Flash"/"Asteel flash" as the
    same string without merging genuinely distinct names (e.g. "Le Golf" vs
    "Le Golfe" stay separate, since only case/accent/whitespace differences
    collapse here, not word-level differences).
    """
    lowered = value.strip().lower()
    ascii_text = unicodedata.normalize("NFKD", lowered).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", ascii_text).strip()


def client_id(client_name: str) -> str:
    """Canonical grouping key for a client name -- merges accent/case/whitespace
    variants (e.g. "Asteel Flash" / "Asteel flash") without merging genuinely
    distinct names."""
    return normalize_text(client_name).replace(" ", "-")
