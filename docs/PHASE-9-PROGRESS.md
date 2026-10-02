# Elsyia Phase 9 Autonomous-Agent Foundation

**Verification date:** August 20, 2026  
**Milestone:** Local agent identity, capability isolation, bounded scheduling, budgets, lifecycle controls, and emergency stop  
**Status:** Foundation implemented and verified

## Completed capabilities

| Capability | Result |
|---|---|
| Local agent identity | Name, purpose, random ID, lifecycle, timestamps |
| Capability isolation | Explicit tool, plugin, domain, and repository-root allowlists |
| Persistent storage | Local SQLite agents, runs, events, and emergency-stop metadata |
| Lifecycle management | Draft, scheduled, running, paused, stopped, blocked, failed, completed, expired states |
| Scheduling | Bounded one-shot and recurring preparation with minimum five-minute interval |
| Budget enforcement | Run, runtime, tool-call, browser, file, and notification limits |
| Run preparation | Creates a persistent run record without executing tools |
| Emergency stop | Persistent global stop blocks new agent starts and pauses active scheduling |
| API | Create, list, inspect, start, pause, stop, run, events, emergency-stop, and clear |
| Scheduler worker | Backend lifecycle worker prepares due runs without bypassing confirmations |
| Desktop UI | `Agents · A` panel with lifecycle controls and emergency stop |
| Safety integration | Existing Phase 8 plan, Phase 6 browser, Phase 5 desktop, Phase 4 plugin, and audit boundaries reused |

## Architecture

```text
Agent API / desktop panel
    -> AgentManager
    -> local SQLite agent/run/event store
    -> lifecycle and budget validator
    -> capability intersection with global registry
    -> scheduler lease and run preparation
    -> approved plan/tool boundary
    -> confirmation_required or prepared result
```

The local backend owns the worker because it already runs on the user’s Windows computer and has access to local reminders, plans, tools, browser sessions, and notifications. The computer must remain online for background preparation. The worker is shutdown-aware and does not execute arbitrary shell commands or silently run external side effects.

## Capability and budget safety

Agent creation validates every allowed tool against the current global registry. An agent cannot add unavailable tools, plugins, domains, or roots. Run preparation records the allowed tool set and increments only bounded run usage. When budgets are exhausted, the agent moves to `blocked` and requires review.

Agent intervals must be at least five minutes and no more than one day in the foundation. Duplicate runs are prevented through lifecycle state and persistent next-run fields. A running agent cannot be prepared again until it is transitioned back through its lifecycle.

## Emergency stop

The emergency stop is persisted in the local agent metadata table. Activating it pauses scheduled/running agents and blocks new starts and run preparation. Clearing it is an explicit user action. All emergency-stop transitions are recorded in local agent events.

## API

```http
POST /api/v1/agents/create
GET  /api/v1/agents
GET  /api/v1/agents/{id}
POST /api/v1/agents/{id}/start
POST /api/v1/agents/{id}/pause
POST /api/v1/agents/{id}/stop
POST /api/v1/agents/{id}/run
GET  /api/v1/agents/{id}/events
GET  /api/v1/agents/emergency-stop
POST /api/v1/agents/emergency-stop
POST /api/v1/agents/emergency-stop/clear
```

Agent run preparation returns `prepared` and explicitly states that no tool was executed. Future workflow execution must revalidate the agent capabilities, plan version, task confirmation, budgets, and emergency-stop state immediately before each task.

## Configuration

```env
AGENTS_ENABLED=true
AGENTS_DB_PATH=data/elysia_agents.db
AGENTS_WORKER_ENABLED=true
AGENTS_POLL_SECONDS=30
AGENTS_MIN_INTERVAL_SECONDS=300
AGENTS_MAX_RUNTIME_SECONDS=120
AGENTS_MAX_ACTIVE=3
AGENTS_MAX_TOOL_CALLS_PER_RUN=10
AGENTS_MAX_NOTIFICATIONS_PER_DAY=10
```

## Verification

| Check | Result |
|---|---|
| Backend compilation | Passed |
| Unknown-tool isolation | Passed |
| Minimum schedule interval validation | Passed |
| Agent lifecycle transitions | Passed |
| Local SQLite persistence | Passed |
| Run and notification budget blocking | Passed |
| Emergency-stop persistence and blocking | Passed |
| Agent event history | Passed |
| Phase 9 API integration | Passed |
| Live root phase marker | Phase 9 |
| Live agent creation | Passed |
| Live scheduling | Passed |
| Live run preparation | Passed; no tool executed |
| Live emergency stop | Passed |
| Live blocked start during emergency stop | Passed |
| Live emergency-stop clear | Passed |
| Phase 8 planning suite | Passed |
| Phase 7 code-assistant suite | Passed |
| Phase 6 browser suite | Passed |
| Phase 5 desktop suite | Passed |
| Phase 4 plugin suite | Passed |
| Existing tool and pytest suites | Passed |
| Frontend TypeScript and production build | Passed |

The existing non-blocking Vite warning about the JavaScript bundle exceeding 500 kB remains.

## Remaining Phase 9 milestones

The next work should add notification policy delivery, file and browser monitor triggers, safe execution of approved Phase 8 plans, retry and recovery workers, and specialized research or personal-assistant agents. Email, calendar, purchases, account changes, autonomous publishing, and inter-agent collaboration require separate integrations and safety reviews.
