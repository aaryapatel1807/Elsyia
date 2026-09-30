# Phase 11 Cloud Sync Foundation

**Phase:** 11 — Cloud Sync  
**Initial milestone:** Encrypted local backup, versioned manifests, and restore preview  
**Status:** In progress

## Scope

Phase 11 begins with a safe synchronization boundary rather than immediately transmitting private data to a third-party cloud. Elsyia creates encrypted, versioned backup packages from selected local SQLite stores and provides manifest inspection, restore preview, and confirmation-gated restore. A future cloud adapter can transport the same encrypted package without receiving plaintext.

The initial sync scope includes memory, plans, agents, and input metadata databases when they exist. Raw attachment files, `.env`, API keys, model caches, logs, browser profiles, and operating-system data are excluded by default.

## Encryption and identity

Backups require a user-supplied Fernet key in `SYNC_ENCRYPTION_KEY`. The key is read only from the local `.env`; it is never generated into chat, logged, or returned by an API. Each installation has a local device ID, persisted in the sync metadata database or configured through `SYNC_DEVICE_ID`.

The encrypted package contains a manifest with schema version, device ID, creation time, included database metadata, SHA-256 digests, and excluded-data declarations. The package does not contain plaintext metadata outside the encrypted payload.

## Restore policy

Restore is two-step. The preview endpoint decrypts and validates the package without changing application data. Actual restore requires an explicit `confirm=true` request and writes databases through a staging directory followed by atomic replacement where possible. Existing databases are copied into a local pre-restore safety backup before replacement. A failed restore must leave the original files untouched.

Restore is local-only in this milestone. It cannot execute code, overwrite arbitrary paths, change `.env`, restore attachments, or modify files outside the configured project data directory.

## Conflict policy

The first cloud-neutral protocol is conservative. Every package has a device ID, monotonically increasing local backup sequence, creation timestamp, schema version, and per-file digest. A future push/pull adapter must detect divergent digests and return a conflict record rather than silently choosing a winner. Automatic last-write-wins is not enabled for memory, plans, agents, or settings.

## Cloud egress

`SYNC_CLOUD_ENABLED` defaults to false. Push and pull requests fail closed until a user explicitly configures a trusted sync endpoint and enables cloud synchronization. Even then, the payload sent to the endpoint is the encrypted package, not plaintext records. Cloud transport, authentication, endpoint allowlisting, and end-to-end key exchange are separate milestones.

## API foundation

```http
GET  /api/v1/sync/status
POST /api/v1/sync/backup
GET  /api/v1/sync/backups
POST /api/v1/sync/restore/preview
POST /api/v1/sync/restore
POST /api/v1/sync/push
GET  /api/v1/sync/pull
```

The push and pull routes are intentionally disabled until the cloud adapter is configured. Backup creation and restore preview remain useful without any cloud account.

## Privacy exclusions

| Data | Default behavior |
|---|---|
| Approved and pending memory records | Included in encrypted local backup |
| Plans and agents databases | Included when present |
| Input attachment metadata database | Included when present |
| Raw attachment files | Excluded |
| API keys and `.env` | Excluded |
| Logs and browser sessions | Excluded |
| Model caches and temporary files | Excluded |

## Acceptance criteria

The initial milestone is complete when Elsyia can create an encrypted backup with a validated manifest, list local backup metadata without exposing contents, preview a restore without changes, reject invalid keys and tampered packages, require explicit restore confirmation, preserve a pre-restore safety copy, and fail closed for cloud push/pull while cloud sync is disabled.
