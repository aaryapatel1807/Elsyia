# Phase 11 Conflict Resolution Progress

**Milestone:** Provider-neutral explicit conflict-resolution protocol  
**Status:** Implemented local protocol; reliable cross-device production sync remains pending

Elsyia now exposes a conflict-resolution endpoint that accepts only metadata decisions for exactly the conflicting database keys. Supported decisions are `keep_local`, `use_remote`, and `skip`; incomplete, extra, or unknown decisions are rejected. Restore accepts the same decisions and selectively skips local-preservation or skip entries, while `use_remote` remains an explicit overwrite. Existing `force=true` behavior remains available as a compatibility path, but the documented safe path is preview, resolve, then confirmation-gated restore.

The protocol returns keys, decisions, status, and confirmation state only. It does not return decrypted package contents or plaintext database data. Existing Fernet package encryption, manifest digests, HMAC-authenticated transport, endpoint allowlists, device enrollment, replay protection, opaque relay behavior, pre-restore safety copies, and atomic replacement remain unchanged. Cloud push/pull remain disabled unless explicitly configured and policy-allowed.

## Verification

The backend compiled successfully. The dedicated Phase 11 suite passed explicit decision coverage, invalid/incomplete decision rejection, selective local-preservation restore, and plaintext-free metadata behavior.
