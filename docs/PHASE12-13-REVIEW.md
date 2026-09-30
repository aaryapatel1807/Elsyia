# Phase 12 and Phase 13 Roadmap Review

## Phase 12 remaining milestones

Phase 12 currently has a strong local enterprise foundation: workspace metadata, roles, policy storage, redacted audit summaries, opt-in analytics, short-lived sessions, revocation, and SSO/MFA readiness boundaries are implemented. The remaining roadmap items are provider-backed SSO, real MFA verification, durable multi-tenancy, team collaboration, shared agents and workflows, comprehensive analytics reporting, billing, priority support, on-premises deployment, and external integrations.

The next safe milestone is **workspace invitations and membership lifecycle**. It directly advances team collaboration and workspace management without inventing an identity provider, email service, billing provider, or cloud tenant model. Invitations will be local, one-time, hashed, expiring records. Accepting an invitation will create a pending or active local member record, but full member login remains dependent on the future identity-provider milestone.

| Remaining Phase 12 item | Current state | Recommended order |
|---|---|---:|
| Team collaboration and workspace membership | Foundation exists; invitations pending | 1 |
| Shared agents and workflows | Agent foundation exists; sharing grants pending | 2 |
| Real MFA verification | Readiness record exists; provider/verifier pending | 3 |
| Provider-backed SSO | Fail-closed boundary exists; provider selection pending | 4 |
| Analytics reporting | Local counters exist; dashboards and export pending | 5 |
| Multi-tenancy and on-premises deployment | Not started | 6 |
| Billing, support, Slack/Teams/Jira integrations | Provider and operations decisions pending | 7 |

## Phase 13 review

The current `docs/ROADMAP.md` ends after Phase 12 and a **Post-Phase 12: Continuous Evolution** section. It does not define a Phase 13 title, objectives, features, technical components, APIs, or success criteria. Therefore, no Phase 13 implementation should be invented as if it were approved. A future Phase 13 should be specified after Phase 12 scope, identity, deployment, compliance, and billing decisions are settled.

The existing Post-Phase 12 initiatives are internationalization, accessibility, performance, customization, community, research, and education. These are ongoing themes rather than a formal Phase 13 contract.
