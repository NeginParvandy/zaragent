from __future__ import annotations

from typing import Any, Protocol

from app.domain.models import AgentContext


class AgentHandler(Protocol):
    """Domain handler that may own an incoming assistant message."""

    async def try_handle(
        self,
        context: AgentContext,
        message: str,
    ) -> dict[str, Any] | None:
        """Return a response when handled, otherwise return ``None``."""
        ...


class AgentFallback(Protocol):
    """Temporary fallback contract used while legacy chat logic is migrated."""

    async def handle(
        self,
        context: AgentContext,
        message: str,
    ) -> dict[str, Any]:
        ...
