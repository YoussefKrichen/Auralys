from __future__ import annotations

from collections import Counter

from app.config import settings
from app.ingestion.normalize import load_fiches_from_directory


def build_ingestion_report(raw_data_dir: str | None = None) -> dict:
    fiches = load_fiches_from_directory(raw_data_dir or settings.raw_data_dir)
    maintenance_fiches = [fiche for fiche in fiches if fiche.document_type == "client_maintenance_form"]
    clients = Counter(fiche.client or "unknown" for fiche in maintenance_fiches)
    service_types = Counter()
    document_types = Counter(fiche.document_type for fiche in fiches)
    for fiche in maintenance_fiches:
        labels = fiche.service_type.active_labels() or ["unknown"]
        service_types.update(labels)
    return {
        "fiches": len(fiches),
        "maintenance_fiches": len(maintenance_fiches),
        "unique_clients": len(clients),
        "top_clients": clients.most_common(10),
        "document_types": document_types.most_common(),
        "service_types": service_types.most_common(),
    }


if __name__ == "__main__":
    print(build_ingestion_report())
