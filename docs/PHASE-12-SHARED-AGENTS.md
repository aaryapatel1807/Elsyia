# Phase 12 Shared-Agent Progress

**Milestone:** Authenticated local shared-agent grants  
**Status:** Implemented boundary; remote federation, billing, and third-party integrations remain pending

Elsyia now provides a local enterprise grant store for sharing an agent with active workspace members. Grants are authenticated with the existing short-lived bearer-session boundary, require an owner or administrator for changes, are scoped to the workspace member identifier, and support only `view` and `prepare_run`. Grant creation validates the agent and target member, and revocation is explicit and durable.

The shared-agent layer does not execute tools, bypass existing agent allowlists, grant external-side-effect authority, or expose agent credentials. Existing emergency-stop, per-agent budgets, plan approval, tool confirmation, audit, and identity readiness boundaries remain authoritative. SSO and MFA are still provider-readiness boundaries rather than enabled external authentication flows.

## Verification

The backend compiled successfully. The dedicated Phase 12 suite passed authenticated grant creation, capability allowlist rejection, member-principal authorization, and revocation behavior.
