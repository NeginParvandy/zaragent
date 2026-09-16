# Option B Architecture - Phase 1

## Goal
Introduce a professional migration seam without rewriting the existing 15k-line `ChatService` in one risky step.

## New request path

`MyZar -> /api/agent/chat -> AgentOrchestrator -> Domain Handlers -> Legacy ChatService fallback`

## What changed

- Added `AgentOrchestrator` as the single application entry point for chat requests.
- Added a handler contract (`AgentHandler`).
- Extracted monthly-attendance routing from `ChatService` into `MonthlyAttendanceHandler`.
- Kept `ChatService` as a fallback so current Food/HR/Attendance/Conversation behavior remains available while domains are migrated one by one.
- Wired the new orchestrator through `Container` and `/api/agent/chat`.

## Next safe extractions

1. Attendance handler (highest business priority).
2. Leave handler.
3. Food conversation handler.
4. Conversation/session manager.
5. Confirmation/pending-action coordinator.

Do not move all domains in a single change. Each extraction should have regression tests before the old code is removed.
