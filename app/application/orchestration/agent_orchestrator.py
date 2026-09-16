from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from app.application.handlers.base import AgentFallback, AgentHandler
from app.domain.models import AgentContext


class AgentOrchestrator:
    """Single application entry point for assistant messages.

    New domain handlers are evaluated in a deliberate order. During migration,
    unhandled requests fall back to the existing chat implementation. This
    provides a safe seam for extracting the legacy 15k-line service without a
    big-bang rewrite.
    """

    def __init__(
        self,
        handlers: Iterable[AgentHandler],
        fallback: AgentFallback,
    ) -> None:
        self._handlers = tuple(handlers)
        self._fallback = fallback

    async def handle(
        self,
        context: AgentContext,
        message: str,
    ) -> dict[str, Any]:
        for handler in self._handlers:
            response = await handler.try_handle(
                context,
                message,
            )
            if response is not None:
                return response

        return await self._fallback.handle(
            context,
            message,
        )
