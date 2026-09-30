# Phase 8 Planning Coordinator Progress

**Milestone:** Local goal decomposition, safe parallel preparation, and bounded retries  
**Status:** Implemented foundation; dynamic replanning and estimation remain pending

Elsyia now exposes a local goal-decomposition endpoint that asks only the configured Ollama provider for a small JSON task draft. The response is bounded by task count, text length, generation time, and safe action classes. If Ollama is unavailable or produces invalid JSON, the service returns a deterministic sequential analysis-only fallback. The result is a draft and is not persisted or executed until the user explicitly creates and approves a plan.

The plan manager can prepare up to the configured number of independent `analysis` or `local_reversible` tasks together. External-side-effect tasks remain confirmation-gated through the existing single-task preparation path. A task-result endpoint records bounded JSON output, increments attempts, schedules a retry only within the task's configured retry budget, and transitions to terminal failure when the budget is exhausted. Cancellation, pause, revision, dependency validation, cycle rejection, and local redacted events remain in force.

This milestone does not claim automatic dynamic replanning from arbitrary observations, conditional branches, time estimation, uncertainty scoring, unattended execution, or high-impact actions. The local model is not permitted to authorize side effects; it only proposes a reviewable draft.

## Configuration

```env
PLAN_DECOMPOSITION_ENABLED=true
PLAN_DECOMPOSITION_TIMEOUT_SECONDS=4
PLAN_MAX_DECOMPOSED_TASKS=12
PLAN_MAX_PARALLEL_TASKS=3
PLAN_MAX_RETRIES=2
```

## Verification

The backend compiled successfully. The dedicated Phase 8 suite passed three checks for deterministic fallback decomposition, independent safe-task preparation with bounded retry behavior, and disabled-decomposition fail-closed behavior.
