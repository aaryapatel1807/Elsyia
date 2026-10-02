"""Verification boundary for signed local plugin package metadata.

This module verifies metadata only; it never installs, downloads, or executes a
package. Unsigned trusted-local plugins remain supported for the bundled local
workflow, while any plugin that presents signature metadata must verify fully.
"""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


class PluginSignatureError(ValueError):
    """Raised when signed plugin metadata cannot be verified."""


def _b64(value: str, label: str) -> bytes:
    try:
        decoded = base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as exc:
        raise PluginSignatureError(f"Invalid base64 {label}.") from exc
    return decoded


def source_sha256(directory: Path) -> str:
    """Hash all plugin files except plugin.json in deterministic path order."""
    digest = hashlib.sha256()
    files = sorted(
        path for path in directory.rglob("*") if path.is_file() and path.name != "plugin.json"
    )
    for path in files:
        relative = path.relative_to(directory).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        content = path.read_bytes()
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def canonical_payload(data: dict[str, Any]) -> bytes:
    """Build the exact UTF-8 payload signed by a package publisher."""
    unsigned = {key: value for key, value in data.items() if key not in {"signature"}}
    return json.dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "utf-8"
    )


def verify_manifest_signature(data: dict[str, Any], directory: Path, trusted_keys: set[str]) -> str:
    """Verify a signed manifest and return its stable public-key fingerprint."""
    algorithm = str(data.get("signature_algorithm", "")).strip().lower()
    public_key_text = str(data.get("public_key", "")).strip()
    signature_text = str(data.get("signature", "")).strip()
    expected_hash = str(data.get("package_sha256", "")).strip().lower()
    if algorithm != "ed25519" or not public_key_text or not signature_text or not expected_hash:
        raise PluginSignatureError("Signed plugins require Ed25519 metadata, public_key, signature, and package_sha256.")
    if expected_hash != source_sha256(directory):
        raise PluginSignatureError("Plugin package hash does not match its local source files.")
    public_key_bytes = _b64(public_key_text, "public key")
    signature_bytes = _b64(signature_text, "signature")
    if len(public_key_bytes) != 32 or len(signature_bytes) != 64:
        raise PluginSignatureError("Ed25519 public keys must be 32 bytes and signatures 64 bytes.")
    fingerprint = hashlib.sha256(public_key_bytes).hexdigest()
    if fingerprint not in trusted_keys:
        raise PluginSignatureError("Plugin signing key is not in the local trusted-key allowlist.")
    try:
        Ed25519PublicKey.from_public_bytes(public_key_bytes).verify(
            signature_bytes, canonical_payload(data)
        )
    except (InvalidSignature, ValueError) as exc:
        raise PluginSignatureError("Plugin signature verification failed.") from exc
    return fingerprint
