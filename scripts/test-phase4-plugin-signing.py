"""Phase 4 plugin SDK and signed-package metadata checks."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core import get_settings  # noqa: E402
from app.services.plugins import PluginManager  # noqa: E402
from app.services.plugins.signing import canonical_payload, source_sha256  # noqa: E402
from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402


def write_plugin(root: Path, name: str, manifest: dict[str, object]) -> None:
    directory = root / name
    directory.mkdir()
    (directory / "plugin.py").write_text(
        "from app.services.tools.base import Tool\n"
        "class TestTool(Tool):\n"
        "    name = 'test_tool'\n"
        "    description = 'Signed plugin test tool'\n"
        "    async def run(self):\n"
        "        return {'ok': True}\n"
        "def create_plugin():\n"
        "    return [TestTool()]\n",
        encoding="utf-8",
    )
    (directory / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")


def main() -> None:
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    fingerprint = hashlib.sha256(public).hexdigest()
    get_settings().PLUGIN_TRUSTED_KEY_FINGERPRINTS = fingerprint

    with TemporaryDirectory() as temporary_dir:
        root = Path(temporary_dir)
        unsigned = {
            "id": "unsigned_local",
            "name": "Unsigned Local",
            "version": "1.0.0",
            "description": "Unsigned trusted-local compatibility test",
            "entrypoint": "plugin.py:create_plugin",
            "tools": ["test_tool"],
            "permissions": [],
            "trusted": True,
            "enabled_by_default": True,
        }
        write_plugin(root, "unsigned_local", unsigned)

        signed = {
            "id": "signed_local",
            "name": "Signed Local",
            "version": "1.0.0",
            "description": "Signed metadata test",
            "entrypoint": "plugin.py:create_plugin",
            "tools": ["test_tool"],
            "permissions": [],
            "trusted": True,
            "enabled_by_default": True,
            "publisher": "Elysia Test Publisher",
            "signature_algorithm": "ed25519",
            "public_key": base64.b64encode(public).decode("ascii"),
        }
        write_plugin(root, "signed_local", signed)
        signed_directory = root / "signed_local"
        signed["package_sha256"] = source_sha256(signed_directory)
        signed["signature"] = base64.b64encode(
            private.sign(canonical_payload(signed))
        ).decode("ascii")
        (signed_directory / "plugin.json").write_text(json.dumps(signed), encoding="utf-8")

        tampered = dict(signed)
        tampered["id"] = "tampered_local"
        tampered_directory = root / "tampered_local"
        tampered_directory.mkdir()
        (tampered_directory / "plugin.py").write_text(
            (signed_directory / "plugin.py").read_text(encoding="utf-8") + "\n# tampered\n",
            encoding="utf-8",
        )
        (tampered_directory / "plugin.json").write_text(json.dumps(tampered), encoding="utf-8")

        manager = PluginManager(root)
        manager.discover(auto_enable=True)
        assert manager.get("unsigned_local").state == "enabled"
        assert manager.get("signed_local").state == "enabled"
        assert manager.get("signed_local").signature_status == "verified"
        assert manager.get("tampered_local").state == "failed"
        assert manager.get("tampered_local").signature_status == "invalid"
        assert "hash" in (manager.get("tampered_local").error or "").lower()

        result = asyncio.run(manager.execute("signed_local", "test_tool", {}))
        assert result.status == "completed"

    print("Phase 4 plugin signing checks passed")


if __name__ == "__main__":
    main()
