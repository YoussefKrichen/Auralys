from __future__ import annotations

from app.agent.tools.emplacement_normalizer import canonical_emplacement


def test_canonical_emplacement_collapses_block_notation_variants():
    variants = ["B1 RDC", "BL1RDC", "Bloc 1 RDC", "RDC B1"]

    keys = {canonical_emplacement(variant) for variant in variants}

    assert len(keys) == 1


def test_canonical_emplacement_keeps_distinct_locations_separate():
    key_b1 = canonical_emplacement("B1 RDC")
    key_b2 = canonical_emplacement("B2 RDC")
    key_couloir = canonical_emplacement("B2 couloir")

    assert key_b1 != key_b2
    assert key_b2 != key_couloir


def test_canonical_emplacement_handles_plus_separator_variants():
    assert canonical_emplacement("BL2A + L") == canonical_emplacement("BL2A L")


def test_canonical_emplacement_ignores_accents_and_case():
    assert canonical_emplacement("Entrée") == canonical_emplacement("entree")


def test_canonical_emplacement_handles_missing_value():
    assert canonical_emplacement(None) == ("sans-emplacement",)
    assert canonical_emplacement("   ") == ("sans-emplacement",)
