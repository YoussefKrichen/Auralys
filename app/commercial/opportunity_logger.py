from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings
from schemas.commercial_schema import AdminAlertEvent


class OpportunityLogger:
    def __init__(self, output_path: str | None = None) -> None:
        self.output_path = Path(output_path or settings.admin_alert_log_path)

    def log(self, event: AdminAlertEvent) -> str:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            **event.model_dump(mode="json"),
        }
        with self.output_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return str(self.output_path)
