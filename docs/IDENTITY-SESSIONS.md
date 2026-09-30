# Phase 12 Identity and Session Readiness

**Milestone:** Provider-neutral identity and short-lived admin sessions  
**Status:** In progress

## Scope

This milestone adds a local session boundary around the existing enterprise admin token. It does not implement an external identity provider, SAML/OIDC login, password authentication, or production MFA verification. External SSO remains disabled unless a future provider-specific adapter is explicitly configured.

The local token is used only to issue a short-lived session. The raw session token is returned once, never stored in plaintext, never logged, and kept by the desktop UI only in memory. Sessions are signed, hashed at rest, expire automatically, and can be revoked.

## Session model

| Property | Policy |
|---|---|
| Session lifetime | Configurable, default 60 minutes |
| Token storage | SHA-256 token hash only |
| Token transport | `Authorization: Bearer <session-token>` |
| Signing | HMAC-SHA-256 with a local signing key |
| Revocation | Immediate local revocation record |
| Renewal | Explicit re-authentication in this milestone |
| Persistence | Local enterprise SQLite only |

## MFA readiness

The identity store includes MFA enrollment records with provider and lifecycle status. An enrollment request records intent and remains `pending_provider_setup` until a reviewed TOTP or provider-backed verifier is implemented. No MFA secret is generated, displayed, or stored by this readiness milestone.

## External SSO

`ENTERPRISE_SSO_ENABLED` defaults to false. The SSO-start route returns a safe disabled response until an OIDC/SAML adapter, issuer allowlist, redirect URI policy, state/nonce validation, and provider-specific secret storage are selected. The application never invents an authorization URL.

## API

```http
GET  /api/v1/admin/auth/status
POST /api/v1/admin/auth/session
POST /api/v1/admin/auth/logout
GET  /api/v1/admin/auth/me
POST /api/v1/admin/auth/sso/start
POST /api/v1/admin/auth/mfa/enroll
```

The existing `X-Elysia-Admin-Token` remains supported as a local bootstrap credential. Administration endpoints accept either that local token or a valid short-lived bearer session.
