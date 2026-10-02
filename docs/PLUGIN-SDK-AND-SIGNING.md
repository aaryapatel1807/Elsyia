# Plugin SDK and Signing Boundary

**Status:** Implemented local SDK and metadata-verification foundation

Elsyia now includes a typed TypeScript client at `frontend/src/sdk/plugins.ts`. It exposes the local plugin catalog, refresh, enable, disable, and execute operations with typed lifecycle, permission, signature, confirmation, and result fields. The client treats the backend as the security authority; it does not make trust decisions in the renderer and it never bypasses confirmation.

The backend accepts optional signed package metadata in `plugin.json`. A signed manifest must declare a publisher, `ed25519` algorithm, base64-encoded public key, base64-encoded signature, and a deterministic SHA-256 hash of all package files other than `plugin.json`. The package hash includes sorted relative paths, lengths, and bytes so source changes are detectable. The public-key SHA-256 fingerprint must be present in the local `PLUGIN_TRUSTED_KEY_FINGERPRINTS` semicolon-separated allowlist. Any malformed, tampered, untrusted, or cryptographically invalid signed package is retained as a failed record and cannot be enabled.

Unsigned bundled plugins remain supported as trusted local extensions for backward compatibility. This is not a marketplace, download service, or arbitrary-code sandbox. The project does not claim production community-plugin distribution, remote package installation, publisher onboarding, or operating-system process isolation. Those require a separately reviewed deployment and security design.

## Configuration

```env
PLUGIN_TRUSTED_KEY_FINGERPRINTS=
```

Leave the allowlist empty unless a local administrator has independently verified a publisher key. Never place private signing keys in the project or in chat.

## Verification

The backend compiled successfully. `scripts/test-phase4-plugin-signing.py` passed checks for unsigned local compatibility, valid Ed25519 metadata, tampered-source rejection, invalid-signature lifecycle blocking, and execution of a verified plugin tool. The TypeScript SDK is included in the frontend strict compilation surface and is covered by the production build gate.
