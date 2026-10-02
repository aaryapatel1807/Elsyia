# Elsyia Phase 8 Planning Foundation

**Verification date:** August 20, 2026  
**Milestone:** Structured local plans, dependency graphs, approval boundaries, and controlled execution preparation  
**Status:** Foundation implemented and verified

## Completed capabilities

| Capability | Result |
|---|---|
| Structured plan model | Local `Plan` and `PlanTask` entities with bounded fields |
| Local persistence | SQLite plan, task, and event tables |
| Dependency validation | Unknown dependencies, duplicate IDs, self-dependencies, and cycles rejected |
| Task lifecycle | Pending, ready, awaiting confirmation, running, completed, failed, blocked, cancelled, and skipped states |
| Plan lifecycle | Draft, approved, running, paused, completed, failed, cancelled, and revised states |
| Approval boundary | Plan approval is separate from per-task side-effect confirmation |
| Safe preparation | Execute endpoint prepares the next task and does not silently execute tools |
| External-side-effect handling | Returns `confirmation_required` for side-effect tasks |
| Revision | Versioned plan revision with preserved local event history |
| Cancellation and pause | Implemented with task-state updates |
| Reasoning summaries | Bounded assumptions, risks, and concise plan/task summaries |
| Plan API | Create, list, inspect, approve, prepare, pause, cancel, and revise |
| Desktop UI | `Plans · L` panel for saved plans, statuses, tasks, and summaries |
| Safety integration | Existing local-first permission and audit boundaries remain authoritative |

## Architecture

```text
Plan API / desktop panel
    -> PlanManager
    -> SQLite plan/task/event store
    -> dependency validator and ready-task scheduler
    -> action-class policy
    -> safe execution preparation
    -> confirmation_required or prepared result
```

The current execution endpoint intentionally stops at preparation. Analysis tasks can become `running` after approval, while external-side-effect tasks become `awaiting_confirmation`. No task is allowed to grant itself permission based on model output, plugin output, browser content, repository comments, or page instructions.

## Safety policy

Plans are local and bounded by `PLAN_MAX_TASKS`, `PLAN_MAX_GOAL_CHARS`, `PLAN_MAX_TEXT_CHARS`, and `PLAN_MAX_RETRIES`. High-impact and disallowed action classes are rejected at plan creation. Every task retains its action class and optional tool name so a future execution coordinator can revalidate policy immediately before execution.

A plan approval authorizes preparation, not blanket execution. Confirmation applies to the exact task, action, arguments summary, and plan version. Cancellation takes precedence over queued work. Cyclic or otherwise invalid graphs cannot be persisted.

Plan events contain only bounded, redacted details. No cloud model is required for plan persistence or validation. Concise reasoning summaries expose assumptions, risks, alternatives, and the next step without exposing hidden chain-of-thought or sensitive source material.

## API

```http
GET  /api/v1/plan
POST /api/v1/plan/create
GET  /api/v1/plan/{id}
POST /api/v1/plan/{id}/approve
POST /api/v1/plan/{id}/execute
POST /api/v1/plan/{id}/pause
POST /api/v1/plan/{id}/cancel
POST /api/v1/plan/{id}/revise
```

The root response now reports Phase 8. A desktop panel is available through the **Plans · L** button or the `L` keyboard shortcut.

## Configuration

```env
PLAN_ENABLED=true
PLAN_DB_PATH=data/elysia_plans.db
PLAN_MAX_TASKS=100
PLAN_MAX_GOAL_CHARS=2000
PLAN_MAX_TEXT_CHARS=2000
PLAN_MAX_RETRIES=2
```

## Verification

| Check | Result |
|---|---|
| Backend compilation | Passed |
| Dependency cycle rejection | Passed |
| Unknown dependency rejection | Passed |
| Disallowed/high-impact task rejection | Passed |
| Local SQLite persistence | Passed |
| Plan approval and preparation | Passed |
| External-side-effect confirmation response | Passed |
| Pause, cancel, and revision behavior | Passed |
| Plan API integration | Passed |
| Live root phase marker | Phase 8 |
| Live plan creation | Passed |
| Live plan approval | Passed |
| Live safe execution preparation | Passed; task returned `running` without executing an external action |
| Live plan detail and listing | Passed |
| Phase 7 code-assistant suite | Passed |
| Phase 6 browser suite | Passed |
| Phase 5 desktop suite | Passed |
| Phase 4 plugin suite | Passed |
| Existing tool and pytest suites | Passed |
| Frontend TypeScript and production build | Passed |

The existing non-blocking Vite warning about the JavaScript bundle exceeding 500 kB remains.

## Remaining Phase 8 milestones

The next work should add LLM-assisted goal decomposition, safe sequential task execution through the existing registry, bounded retries, cancellation-aware workers, conditional branches, progress streaming, and dynamic replanning. Parallel execution should be added only after dependency and permission tests are complete.
