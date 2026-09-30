# Phase 11 Progress Report: Cloud Sync Foundation

**Project:** Elsyia  
**Phase:** 11 — Cloud Sync  
**Milestone:** Encrypted local backup, manifest validation, restore preview, and desktop sync controls  
**Status:** In progress  
**Author:** Manus AI

## Summary

Phase 11 has started with a cloud-neutral synchronization foundation. Elsyia can create encrypted local backup packages containing selected application databases, inspect their authenticated manifests, preview restore effects, detect conflicts, and restore only after explicit confirmation. Cloud push and pull are fail-closed and do not transmit or receive data in this milestone.

This order preserves the local-first requirement: a future cloud adapter can transport an already encrypted package rather than receiving plaintext memory, plans, agents, or settings records.

## Implemented capabilities

| Capability | Status |
|---|---|
| Fernet-encrypted sync package | Complete |
| Versioned manifest | Complete |
| Local device identity | Complete |
| Monotonic backup sequence | Complete |
| SHA-256 per-database digest metadata | Complete |
| Memory, plans, agents, and input-metadata database scope | Complete |
| Raw attachment, `.env`, API-key, log, browser-profile, cache, and temporary-file exclusion | Complete |
| Local backup listing and bounded retention | Complete |
| Authenticated tamper detection | Complete |
| Restore preview without data changes | Complete |
| Conflict detection | Complete |
| Explicit restore confirmation and optional force-overwrite | Complete |
| Pre-restore safety copies | Complete |
| Staged writes and atomic replacement | Complete |
| Cloud push/pull adapter | Deferred; routes fail closed |
| Mobile, web, shared conversations, and settings sync | Deferred |

## API

```http
GET  /api/v1/sync/status
POST /api/v1/sync/backup
GET  /api/v1/sync/backups
POST /api/v1/sync/restore/preview
POST /api/v1/sync/restore
POST /api/v1/sync/push
GET  /api/v1/sync/pull
```

Backup packages require `SYNC_ENCRYPTION_KEY` in the local `.env`. The key is never returned or logged. Cloud transport remains disabled unless `SYNC_CLOUD_ENABLED=true` and an endpoint is explicitly configured, but even that configuration currently returns a no-transmission response until a reviewed adapter is implemented.

## Desktop integration

The new **Sync · S** panel displays the local device ID, cloud-disabled status, backup count, backup creation control, backup metadata, restore preview, conflict states, and confirmation-gated restore actions. A pre-restore safety directory is reported after successful restoration.

## Verification

The Phase 11 regression suite passed four tests covering encrypted package contents, raw attachment exclusion, manifest inspection, restore conflict detection, explicit confirmation, forced restoration, pre-restore safety copies, tamper rejection, and invalid-key failure. Backend compilation passed, the frontend production build passed, and live verification confirmed phase marker 11, sync status, sync routes, backup creation, backup listing, and restore preview.

## Remaining work

The next Phase 11 milestones are a reviewed encrypted-package transport adapter, authenticated endpoint allowlisting, device enrollment, pull/push change exchange, conflict resolution records, optional self-hosted deployment, and mobile/web clients. No cloud provider or remote endpoint should be selected until the user specifies the intended deployment and authentication model.

## Next milestone: authenticated transport and deployment model

The authenticated sync milestone is now implemented. Desktop push and pull requests use HMAC-SHA-256 signatures over the method, exact path, timestamp, nonce, request ID, and encrypted-package body digest. Requests include device identity and are rejected when the endpoint origin is not explicitly allowlisted, when HTTPS requirements are violated, when the clock skew is too large, or when the shared token is missing.

The optional self-hosted relay is available under `/api/v1/sync-relay/push` and `/api/v1/sync-relay/pull`, but it is not mounted unless `SYNC_RELAY_ENABLED=true`. The relay stores opaque encrypted packages only, authenticates enrolled devices, persists replay records, applies package-size limits, and never decrypts package contents. The default desktop installation remains cloud-disabled and makes no remote requests.

### Authentication settings

`SYNC_AUTH_TOKEN` is the local device-to-relay secret. `SYNC_ENDPOINT_ALLOWLIST` contains exact allowed origins, while `SYNC_CLOUD_ENDPOINT` contains the configured relay path. `SYNC_ALLOW_LOOPBACK_HTTP` is intended only for local development; production deployment requires HTTPS. Device allowlisting is configured on the relay with `SYNC_RELAY_ALLOWED_DEVICES`.

### Verification update

Backend compilation passed. The Phase 11 authentication suite passed six tests covering HMAC verification, body tampering, stale timestamps, replay rejection, endpoint allowlisting, loopback policy, disabled transport, authenticated push headers, and relay push/pull behavior. The frontend build passed. The relay test used an in-memory test application and confirmed that replayed requests receive HTTP 401 and that pulled packages remain byte-identical opaque payloads.

The remaining Phase 11 work is production deployment hardening, TLS/reverse-proxy configuration, a selected managed-provider adapter if desired, multi-device conflict exchange, revocation UX, and mobile/web clients.
