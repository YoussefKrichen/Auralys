from __future__ import annotations

import re

from app.agent.tools.text_normalize import normalize_text

_BLOCK_PATTERN = re.compile(r"b\.?l?(?:oc)?\.?\s*(\d)")


def canonical_emplacement(raw: str | None) -> tuple[str, ...]:
    """Collapse the many ways technicians abbreviate a diffuser location into one key.

    Field notes across visits mix "Bloc N", "BL{n}", and "B{n}" interchangeably, in
    any word order (e.g. "B1 RDC" / "BL1RDC" / "Bloc 1 RDC" / "RDC B1" are the same
    physical location) -- validated against real Aromair maintenance data.
    """
    if not raw or not raw.strip():
        return ("sans-emplacement",)
    normalized = normalize_text(raw)
    match = _BLOCK_PATTERN.search(normalized)
    block = match.group(1) if match else None
    rest = (normalized[: match.start()] + normalized[match.end() :]) if match else normalized
    rest = rest.replace("+", " ")
    rest = re.sub(r"\s+", " ", rest).strip()
    words = sorted(word for word in rest.split(" ") if word)
    return (("bloc" + block) if block else "no-block",) + tuple(words)
