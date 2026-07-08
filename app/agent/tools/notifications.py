from __future__ import annotations

from typing import Any


class NotificationsTool:
    def send_client_message(self, client_id: str, message: str) -> dict[str, Any]:
        return {
            "client_id": client_id,
            "message": message,
            "status": "DISABLED_IN_BETA",
        }

