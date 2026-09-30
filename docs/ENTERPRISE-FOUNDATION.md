# Phase 12 Enterprise Foundation

**Milestone:** Local workspace administration, role policy, audit controls, and opt-in analytics  
**Status:** In progress

## Scope

Phase 12 begins with a local-first administration boundary. It does not claim to implement SSO, MFA, billing, multi-tenant cloud hosting, or compliance certification. Those capabilities require an identity provider, deployment environment, legal controls, and security review that are not selected yet.

The initial foundation provides a workspace record, owner/admin/member/viewer roles, explicit local policies, redacted audit summaries, and privacy-safe analytics counters. Administrative endpoints require `X-Elysia-Admin-Token` and fail closed when `ENTERPRISE_ADMIN_TOKEN` is empty.

## Roles

| Role | Intended authority |
|---|---|
| `owner` | Local workspace owner; may change workspace policy and manage members |
| `admin` | May manage members and read administration data; sensitive policy changes can require owner authority in a future identity-backed milestone |
| `member` | Normal assistant user; no enterprise administration authority |
| `viewer` | Read-only workspace observer |

The local MVP authenticates the administrative control plane with one environment-managed token because no external identity provider has been selected. It does not pretend to identify multiple human users.

## Default policies

| Policy | Default | Meaning |
|---|---:|---|
| `require_confirmation_for_risky_tools` | `true` | Preserve existing confirmation gates |
| `allow_cloud_sync` | `false` | Block cloud push/pull until explicit enterprise approval and sync configuration |
| `allow_autonomous_agents` | `true` | Preserve the existing bounded agent foundation |
| `allow_browser_automation` | `true` | Preserve existing browser allowlists and read-only controls |
| `allow_desktop_automation` | `true` | Preserve existing safe-root and confirmation controls |
| `analytics_opt_in` | `false` | Do not collect usage counters until explicitly enabled |

Policies are stored locally in SQLite and are evaluated by shared helper functions. They never override lower-level safety controls; enabling a policy cannot bypass confirmation, safe roots, budgets, endpoint allowlists, or emergency stops.

## Audit and analytics

Audit administration exposes aggregate counts and recent redacted event metadata only. It never returns raw tool arguments, conversation text, file contents, tokens, URLs with credentials, or attachment paths. Analytics counters are local, bounded, opt-in, and retained for a configured period. No analytics event is transmitted externally.

## API foundation

```http
GET    /api/v1/admin/status
GET    /api/v1/admin/workspace
PATCH  /api/v1/admin/workspace
GET    /api/v1/admin/members
POST   /api/v1/admin/members
PATCH  /api/v1/admin/members/{member_id}
DELETE /api/v1/admin/members/{member_id}
GET    /api/v1/admin/policies
POST   /api/v1/admin/policies
GET    /api/v1/admin/audit/summary
GET    /api/v1/admin/analytics
```

## Remaining enterprise milestones

The next milestones are provider-backed SSO/OIDC, MFA, durable multi-tenant isolation, workspace invitations, enterprise deployment, signed policy bundles, compliance evidence workflows, billing, support operations, and reviewed external integrations. They must not be inferred from the local admin token implementation.
