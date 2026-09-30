# Phase 9 Monitoring Progress

**Milestone:** Local file/metric monitors and in-app notification policy  
**Status:** Implemented local foundation; external delivery and full workflow execution remain pending

Elsyia now supports approved local file and metric monitors. File monitors require an existing non-symlink file under an agent's explicitly allowed local root. Metric monitors accept only the bounded local metrics `runs_used`, `notifications_today`, and `active`, with a fixed comparison-operator allowlist. Each monitor establishes a baseline before emitting a notification, and changes are deduplicated by persisted state.

Notifications are stored in the local agent database and exposed through list and acknowledgement endpoints. Notification content, source identifiers, and event payloads are bounded. Every alert consumes the agent's daily notification budget and is dropped when that budget is exhausted. The existing persistent emergency stop and scheduler exception isolation remain active; monitor evaluation does not execute tools, send email, or contact a third-party service.

This milestone does not claim email or calendar delivery, website polling, inter-agent messaging, learning-agent behavior, unattended workflow execution, or arbitrary event-bus integrations. Those remain explicit future boundaries requiring provider credentials, privacy review, and separate confirmation policies.

## Verification

The backend compiled successfully. The dedicated Phase 9 suite passed checks for safe-root file monitoring, baseline and change detection, notification deduplication, notification budget enforcement, metric allowlisting, and comparison operators.
