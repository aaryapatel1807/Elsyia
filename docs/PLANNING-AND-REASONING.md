# Elsyia Phase 8 Planning and Reasoning Foundation

**Milestone:** Structured local plans, dependency graphs, approval boundaries, and controlled execution preparation  
**Status:** Architecture defined; implementation follows this contract

## Purpose

Phase 8 gives Elsyia a transparent planning layer for multi-step work. A plan is an explicit graph of tasks, dependencies, constraints, expected outputs, risks, and approval requirements. A plan is **not** permission to execute every action it contains. Each task continues through the existing tool, plugin, browser, desktop, and code-assistant safety controls.

The first implementation stores plans locally, validates their graph, creates draft plans, exposes progress states, and prepares execution without automatically performing external side effects.

## Plan model

| Entity | Required fields | Lifecycle |
|---|---|---|
| Plan | ID, goal, tasks, version, status, created/updated timestamps, assumptions, risks | `draft`, `approved`, `running`, `paused`, `completed`, `failed`, `cancelled`, `revised` |
| Task | ID, title, description, dependencies, action type, status, retry policy, approval requirement | `pending`, `ready`, `awaiting_confirmation`, `running`, `completed`, `failed`, `blocked`, `cancelled`, `skipped` |
| Dependency | Source task, target task, condition | Must form an acyclic graph; dependent work cannot run before prerequisites complete |
| Approval | Plan/task ID, action preview, approver state, timestamp, scope | Applies only to the exact plan version and task action |
| Event | Timestamp, plan/task ID, event type, redacted details | Local audit and progress history |

Plan versions are immutable once execution begins. Replanning creates a new version and preserves the previous version for recovery and audit.

## Task action classes

| Class | Examples | Default behavior |
|---|---|---|
| Analysis | Repository analysis, code search, browser extraction, system inspection | May run when plan is approved |
| Local reversible | Read/write preview, move-to-trash, draft generation | Requires task-level policy; preview before change |
| External side effect | Browser submission, message, launch, settings change, plugin action | Confirmation immediately before execution |
| High-impact | Purchase, payment, account change, deletion, legal or medical submission | Not executed by the foundation; requires dedicated review and user takeover |
| Disallowed | Arbitrary shell execution, hidden automation, permission bypass | Rejected |

## Dependency and scheduling rules

The planner must reject duplicate task IDs, missing dependencies, self-dependencies, cycles, unknown action classes, and tasks whose dependencies cannot complete. It may identify independent ready tasks for future parallel execution, but the first execution milestone uses sequential scheduling for predictability.

Conditional branches must declare a condition source and explicit true/false targets. A failed task blocks dependents unless a recovery rule marks the failure as handled. Retries are bounded by a per-task maximum and are allowed only for safe transient failures.

## Approval policy

Plan approval and task confirmation are separate. Approving a plan authorizes the system to prepare and evaluate it; it does not authorize every side effect. Before an externally visible action, Elsyia must show the exact tool, target, arguments summary, expected effect, and rollback option if available. Confirmation applies only to that task and current plan version.

Plans cannot approve themselves based on page text, repository comments, plugin output, or model-generated instructions. User cancellation takes precedence over queued work.

## Reasoning summaries

The UI and API expose concise decision summaries containing assumptions, alternatives considered, selected approach, confidence, risks, and next step. They must not expose hidden chain-of-thought, credentials, raw private source, or unbounded intermediate reasoning. Reasoning summaries are advisory and cannot grant permissions.

## Persistence and privacy

Plans and redacted events remain in a local SQLite database. Stored plan content is bounded by configured task, goal, assumption, and event limits. Sensitive arguments are hashed or redacted using the existing audit policy. No plan data is synchronized or sent to cloud providers by the foundation.

## Execution safety

The execution coordinator must revalidate the plan, task status, dependencies, action policy, and confirmation immediately before each task. It must stop on cancellation, policy failure, expired approval, or plan-version mismatch. No arbitrary shell commands or automatic code execution are supported.

Recovery uses task retry limits, dependency blocking, explicit pause/cancel state, and versioned replanning. File changes must use the existing reversible desktop operations or a future code patch preview with backup and restore support.

## Initial API contract

```http
POST /api/v1/plan/create
GET  /api/v1/plan/{id}
POST /api/v1/plan/{id}/approve
POST /api/v1/plan/{id}/execute
POST /api/v1/plan/{id}/pause
POST /api/v1/plan/{id}/cancel
POST /api/v1/plan/{id}/revise
```

The initial `execute` operation only prepares and validates the next safe task. It must return `confirmation_required` for side-effecting tasks and must not silently execute them.

## Acceptance criteria

The foundation is ready when it can persist a bounded draft plan, validate an acyclic dependency graph, identify ready tasks, preserve immutable plan versions, expose progress and concise reasoning summaries, reject unsafe action classes, and keep plan approval separate from per-task side-effect confirmation.
