from __future__ import annotations

import asyncio
from typing import Any

from app.application.orchestration.agent_orchestrator import AgentOrchestrator
from app.domain.models import AgentContext


class PassHandler:
    async def try_handle(
        self,
        context: AgentContext,
        message: str,
    ) -> dict[str, Any] | None:
        return None


class OwningHandler:
    async def try_handle(
        self,
        context: AgentContext,
        message: str,
    ) -> dict[str, Any] | None:
        return {"reply": "owned"}


class Fallback:
    def __init__(self) -> None:
        self.calls = 0

    async def handle(
        self,
        context: AgentContext,
        message: str,
    ) -> dict[str, Any]:
        self.calls += 1
        return {"reply": "fallback"}


async def main() -> None:
    context = AgentContext()

    fallback = Fallback()
    orchestrator = AgentOrchestrator(
        handlers=(PassHandler(),),
        fallback=fallback
    )
    result = await orchestrator.handle(context, "hello")
    assert result == {"reply": "fallback"}
    assert fallback.calls == 1

    fallback = Fallback()
    orchestrator = AgentOrchestrator(
        handlers=(OwningHandler(),),
        fallback=fallback
    )
    result = await orchestrator.handle(context, "report")
    assert result == {"reply": "owned"}
    assert fallback.calls == 0

    print("AGENT_ORCHESTRATOR_V1_TESTS_OK")


if __name__ == "__main__":
    asyncio.run(main())
