# Phase 11 Sync Authentication and Deployment Model

**Milestone:** Authenticated encrypted-package transport  
**Status:** In progress

## Recommended deployment choices

| Deployment model | Characteristics | Privacy and operations | Current support |
|---|---|---|---|
| **Self-hosted sync relay** | User runs a small HTTPS service under their own domain or LAN | Best control; user manages TLS, backups, authentication, and availability | Protocol-ready; relay deployment is the next server milestone |
| **Managed sync endpoint** | A hosted service receives encrypted packages through the same protocol | Easier availability; requires trust in the operator and explicit endpoint configuration | Client transport-ready; provider adapter not selected |
| **Local-only encrypted backups** | No network transport; packages remain on the desktop | Zero cloud exposure; useful immediately | Fully implemented |

Phase 11 will not choose a provider or transmit data without a user-configured endpoint, allowlist, and authentication secret.

## Authentication protocol

Each request is authenticated with an HMAC-SHA-256 signature over the HTTP method, normalized path, timestamp, nonce, request ID, and body digest. The shared token is stored only in the local `.env` as `SYNC_AUTH_TOKEN`; it is never written to logs, manifests, database records, URLs, or chat.

Required headers:

```text
X-Elysia-Device
X-Elysia-Request-Id
X-Elysia-Timestamp
X-Elysia-Nonce
X-Elysia-Body-SHA256
Authorization: Elysia-HMAC <hex-signature>
```

A receiving relay must verify the exact endpoint path, HTTPS transport, body digest, timestamp skew, nonce uniqueness, device enrollment, and HMAC signature before accepting a package. It must return a conflict response rather than silently overwriting a divergent package.

## Device enrollment

Enrollment is explicit and out-of-band. The relay issues a per-device token after the user confirms the device ID and endpoint. Elsyia stores only the device ID locally and reads the shared token from `.env`. Device IDs are not secrets; tokens are secrets. Revocation is performed at the relay and by removing or rotating `SYNC_AUTH_TOKEN` locally.

## Endpoint policy

Cloud transport is blocked unless all conditions hold:

1. `SYNC_CLOUD_ENABLED=true`.
2. `SYNC_CLOUD_ENDPOINT` is configured.
3. The exact endpoint origin appears in `SYNC_ENDPOINT_ALLOWLIST`.
4. `SYNC_AUTH_TOKEN` is present.
5. The endpoint uses HTTPS, except explicit loopback HTTP for local relay development.
6. The request body is an authenticated encrypted package.

Redirects are disabled. DNS rebinding and private-target protections belong in the relay deployment and future network policy; the client does not follow redirects or accept a changed origin.

## Replay protection

Every request receives a cryptographically random request ID and nonce. The client stores recently used request IDs and nonces locally for the configured replay window. The relay must store the same values server-side and reject duplicates or timestamps outside the allowed clock skew. A retry must use a fresh request ID and nonce.

## Deployment requirements

A self-hosted relay deployment must provide HTTPS, a private secret store, a persistent database for device enrollment and replay records, encrypted-at-rest package storage, authentication failure rate limits, request-size limits, and regular backups. The relay must never decrypt packages as part of transport. Decryption remains on enrolled devices.

A managed endpoint must provide the same protocol behavior, a documented retention policy, authenticated deletion, auditability, and a clear data-processing agreement. No managed provider is selected in this milestone.

## Self-hosted relay implementation

The repository now includes an optional relay under `/api/v1/sync-relay/push` and `/api/v1/sync-relay/pull`. It is not mounted unless `SYNC_RELAY_ENABLED=true`. The relay stores only opaque encrypted packages, authenticates HMAC-signed requests, enforces `SYNC_RELAY_ALLOWED_DEVICES` when configured, rejects stale or replayed requests, limits package size, and persists replay records in SQLite.

For a local development relay, configure the desktop with `SYNC_CLOUD_ENDPOINT=http://127.0.0.1:8000/api/v1/sync-relay`, `SYNC_ENDPOINT_ALLOWLIST=http://127.0.0.1:8000`, `SYNC_ALLOW_LOOPBACK_HTTP=true`, `SYNC_CLOUD_ENABLED=true`, and a matching `SYNC_AUTH_TOKEN`/`SYNC_RELAY_SHARED_TOKEN`. Production deployment must use HTTPS, a reverse proxy or TLS-capable server, a private relay secret store, a persistent relay database and package directory, a non-empty device allowlist, firewall restrictions, and regular encrypted storage backups.

The relay is a transport boundary, not a plaintext synchronization service. It does not decrypt packages or resolve application-level conflicts. Devices must preview and explicitly confirm restores locally.
