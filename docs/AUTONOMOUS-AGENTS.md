# Elsyia Phase 9 Autonomous Agents Foundation

**Milestone:** Local agent identity, capability allowlists, persistent lifecycle, bounded schedules, budgets, and emergency stop  
**Status:** Architecture defined; implementation follows this contract

## Purpose

Phase 9 introduces background agents that can prepare or run approved work without turning Elsyia into an unrestricted autonomous executor. Every agent has a narrow identity, explicit purpose, allowed tools, allowed plugins, optional plan scope, schedule, resource budget, notification policy, and lifecycle state.

> An agent is never granted global permission. Each run is revalidated against the agent allowlist, the Phase 8 plan policy, and the existing tool or plugin confirmation policy.

## Agent model

| Field | Policy |
|---|---|
| Identity | Random local ID, user-visible name, purpose, version, creation/update timestamps |
| Capabilities | Explicit tool names, plugin IDs, browser domains, repository roots, and desktop safe roots |
| Schedule | One-shot or bounded interval; no uncontrolled high-frequency polling |
| Budget | Maximum runs, runtime seconds, tool calls, browser requests, file operations, model tokens, and notifications |
| Lifecycle | `draft`, `stopped`, `scheduled`, `running`, `paused`, `blocked`, `failed`, `completed`, `expired` |
| Approval | Agent creation and start are explicit user actions; high-impact tasks still require task-level confirmation |
| Persistence | Local SQLite only; no agent configuration is uploaded or synchronized |

## Capability isolation

An agent can call only capabilities listed in its configuration. The allowlist is intersected with the global registry: removing or disabling a core tool, plugin, browser domain, or repository root immediately removes that capability from the agent.

Agents cannot add tools, plugins, domains, roots, budgets, schedules, or permissions to themselves. Agent messages are data, not policy. An agent cannot delegate a restricted action to another agent to bypass its own permissions.

## Scheduling policy

The first worker supports bounded one-shot and interval schedules. Intervals must be at least five minutes unless a future dedicated monitor mode is reviewed. Each schedule has a next-run timestamp, maximum run count, and missed-run policy. Duplicate runs are prevented with a persistent lease and `running` state.

The local backend worker is the correct execution host for this desktop-first product because it already owns the user’s local data, Windows notifications, tool registry, browser contexts, and startup lifecycle. The machine must remain online for background work to run.

## Budget policy

Every run consumes an agent budget. When any configured budget is exhausted, the run is blocked and the agent requires user review. Timeouts, retries, browser requests, tool calls, file operations, and notifications are counted independently. Budgets reset only according to the explicit agent configuration; they never reset because an agent requests it.

## Lifecycle and emergency stop

The lifecycle manager supports create, approve, start, pause, stop, run-now, expire, and recover. A global emergency stop sets a local stop flag, prevents new runs, requests active workers to stop, and records an audit event. The stop state persists across backend restarts until the user explicitly clears it.

Shutdown cancels worker tasks and releases leases. A crashed run is marked failed with a bounded recovery record; it is never silently retried without checking the retry budget and agent state.

## Notifications

Notifications are opt-in per agent and bounded by daily and per-run limits. Quiet hours, priority, batching, and dismissal are stored locally. Notifications never contain secrets or unrestricted page/source content. External messages and account changes remain confirmation-gated.

## API foundation

```http
POST /api/v1/agents/create
GET  /api/v1/agents
GET  /api/v1/agents/{id}
POST /api/v1/agents/{id}/start
POST /api/v1/agents/{id}/pause
POST /api/v1/agents/{id}/stop
POST /api/v1/agents/{id}/run
GET  /api/v1/agents/{id}/events
POST /api/v1/agents/emergency-stop
POST /api/v1/agents/emergency-stop/clear
```

Agent start and run-now endpoints prepare a run and return a structured status. A task with an external side effect returns `confirmation_required` and remains pending until the user confirms the exact task.

## Threat model

| Threat | Mitigation |
|---|---|
| Agent self-escalation | Immutable per-run capability intersection and global registry checks |
| Duplicate scheduled runs | Persistent run lease and running state |
| Runaway resource use | Per-agent and per-run budgets plus timeouts |
| Silent external action | Existing confirmation gates remain active per task |
| Restart duplication | Persistent next-run and lease state |
| Malicious agent output | Output treated as untrusted data; cannot modify policy |
| Notification spam | Quiet hours, per-run and daily limits |
| Emergency failure | Persistent global stop flag and startup enforcement |
| Data leakage | Local SQLite, redacted audit details, bounded outputs |

## Foundation acceptance criteria

The foundation is ready when an agent can be created with explicit capabilities and budgets, persisted locally, started and stopped safely, scheduled without duplicate runs, blocked when budgets expire, prevented from calling unlisted tools, and halted by a persistent emergency stop.

The foundation does not include unrestricted email, calendar, purchases, autonomous publishing, arbitrary shell execution, credential handling, or agent collaboration. Those require separate integrations and safety reviews.
