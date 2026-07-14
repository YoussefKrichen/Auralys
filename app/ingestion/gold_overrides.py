from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

GOLD_LAYER_PATH = Path("data/gold/client_address_gold.json")


@lru_cache(maxsize=1)
def _load_gold_records() -> dict[str, dict]:
    if not GOLD_LAYER_PATH.exists():
        return {}
    records = json.loads(GOLD_LAYER_PATH.read_text(encoding="utf-8"))
    return {record["fiche_id"]: record for record in records if record.get("fiche_id")}


def get_gold_client_address(fiche_id: str) -> tuple[str | None, str | None] | None:
    """Return (client_gold, address_gold) for a fiche reconciled against the
    client/address reference registry, or None if this fiche hasn't been through
    that review (see the client_address_gold build in data/gold/)."""
    record = _load_gold_records().get(fiche_id)
    if not record:
        return None
    return record.get("client_gold"), record.get("address_gold")
