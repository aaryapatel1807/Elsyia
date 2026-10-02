# Remaining Work Plan

**Project:** Elsyia  
**Scope:** Unfinished work across Phases 3–12 and Post-Phase 12 initiatives  
**Status:** Execution plan created; implementation proceeds milestone by milestone

## Completion policy

A phase is marked complete only when its explicitly listed features, safety boundaries, documentation, regression tests, and build gates pass. Existing foundations are not treated as full completion when the roadmap still lists material capabilities as pending. External services remain disabled until a provider, credential, endpoint, privacy policy, and rollback path are explicitly configured.

## Dependency-ordered milestones

| Order | Area | First remaining milestone | Main dependency | Completion evidence |
|---:|---|---|---|---|
| 1 | Phase 3 | Local screen capture, OCR, and privacy-bounded vision interface | A local OCR/vision implementation or explicit configured provider | Tests for capture consent, redaction, bounds, and no-cloud default |
| 2 | Phase 4 | TypeScript SDK and signed package metadata boundary | Existing trusted manifest contract | SDK compile tests, signature rejection tests, package limits |
| 3 | Phase 5 | Additional allowlisted Windows settings controls | Existing confirmation and audit layer | Windows capability tests and confirmation coverage |
| 4 | Phase 6 | Guarded screenshots, downloads, and non-sensitive interactions | Browser session policy and confirmation boundary | Domain, file, size, redirect, and confirmation tests |
| 5 | Phase 7 | Semantic code search and richer static analysis | Local embedding availability and metadata-only policy | Index privacy, bounded search, and fallback tests |
| 6 | Phase 8 | LLM-assisted goal decomposition and bounded retry coordinator | Existing plan lifecycle and task action classes | Dependency, retry, approval, cancellation, and budget tests |
| 7 | Phase 9 | File/metric monitor triggers and notification policy | Agent budgets, emergency stop, and local notification channel | Trigger deduplication, rate limits, stop-state, and audit tests |
| 8 | Phase 10 | Clipboard, screenshot, camera, and handwriting input adapters | Input abstraction and retention policy | Consent, sensitive-content redaction, payload, and cleanup tests |
| 9 | Phase 11 | Provider-neutral sync adapter and conflict resolution protocol | Authenticated encrypted-package transport | Replay, conflict, rollback, and no-plaintext tests |
| 10 | Phase 12 | Shared-agent grants and provider-backed identity adapter boundary | Enterprise roles, sessions, and invitations | Capability checks, tenant isolation, revocation, and audit tests |
| 11 | Post-Phase 12 | Complete panel localization, accessibility, and performance budgets | Stable frontend shell and translation resources | Locale, keyboard, screen-reader, and bundle/latency checks |
| 12 | Final | Cross-phase regression and formal roadmap audit | All preceding milestones | Full test matrix, build, security review, and updated reports |

## Explicitly not claimed yet

The following require a user/provider decision before production implementation: paid billing, priority support operations, managed cloud hosting, external email delivery, provider-specific OIDC/SAML credentials, real MFA verification service, Slack/Teams/Jira credentials, mobile distribution, and compliance certification. Local test doubles or fail-closed interfaces may be implemented, but they must not be described as production integrations.

## Operating constraints

All milestones retain local-first defaults, safe-root and allowlist enforcement, confirmation gates for risky actions, redacted audit logging, bounded payloads and concurrency, explicit retention, and emergency-stop behavior. Every milestone receives its own documentation and regression script before the roadmap status changes.
