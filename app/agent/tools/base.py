from __future__ import annotations

from typing import Any, Callable

from app.agent.store import AgentStore


class LoggedTool:
    def __init__(self, store: AgentStore | None = None) -> None:
        self.store = store

    def _run_logged(
        self,
        tool_name: str,
        input_json: dict[str, Any],
        func: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        try:
            output_json = func()
            self._safe_save_tool_log(
                tool_name=tool_name,
                input_json=input_json,
                output_json=output_json,
                success=True,
            )
            return output_json
        except Exception as exc:
            self._safe_save_tool_log(
                tool_name=tool_name,
                input_json=input_json,
                output_json={},
                success=False,
                error_message=str(exc),
            )
            raise

    def _safe_save_tool_log(
        self,
        *,
        tool_name: str,
        input_json: dict[str, Any],
        output_json: dict[str, Any],
        success: bool,
        error_message: str | None = None,
    ) -> None:
        if self.store is None:
            return
        try:
            self.store.save_tool_log(
                tool_name=tool_name,
                input_json=input_json,
                output_json=output_json,
                success=success,
                error_message=error_message,
            )
        except Exception:
            # Tool logging is best-effort and must not break agent execution.
            return
