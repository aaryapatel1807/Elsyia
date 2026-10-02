"""Contracts for Elysia local plugins."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.services.tools.base import Tool

_PLUGIN_ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
_ALLOWED_PERMISSIONS = frozenset(
    {
        "read_local_files",
        "write_local_files",
        "network",
        "launch_application",
        "notifications",
    }
)
_CONFIRMATION_PERMISSIONS = frozenset(
    {"write_local_files", "network", "launch_application", "notifications"}
)


class PluginError(Exception):
    """Expected plugin validation, loading, or execution error."""


@dataclass(frozen=True)
class PluginManifest:
    """Validated metadata declared by a plugin.json file."""

    plugin_id: str
    name: str
    version: str
    description: str
    entrypoint: str
    tool_names: tuple[str, ...]
    permissions: frozenset[str] = frozenset()
    enabled_by_default: bool = False
    trusted: bool = False
    publisher: str = ""
    signature_algorithm: str = ""
    public_key: str = ""
    signature: str = ""
    package_sha256: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PluginManifest":
        plugin_id = str(data.get("id", "")).strip()
        if not _PLUGIN_ID_RE.fullmatch(plugin_id):
            raise PluginError("Plugin id must be lowercase snake_case and 2-64 characters.")
        name = str(data.get("name", "")).strip()
        version = str(data.get("version", "")).strip()
        description = str(data.get("description", "")).strip()
        entrypoint = str(data.get("entrypoint", "")).strip()
        if not name or not version or not description:
            raise PluginError("Plugin name, version, and description are required.")
        if ":" not in entrypoint:
            raise PluginError("Plugin entrypoint must use module.py:function syntax.")
        module_name, function_name = entrypoint.split(":", 1)
        if not module_name.endswith(".py") or not function_name.isidentifier():
            raise PluginError("Plugin entrypoint must reference a Python file and function.")
        raw_tools = data.get("tools", [])
        if not isinstance(raw_tools, list) or not raw_tools:
            raise PluginError("Plugin must declare at least one tool name.")
        tool_names = tuple(str(tool).strip() for tool in raw_tools)
        if any(not tool or not tool.isidentifier() for tool in tool_names):
            raise PluginError("Plugin tool names must be valid identifiers.")
        if len(set(tool_names)) != len(tool_names):
            raise PluginError("Plugin tool names must be unique.")
        signature_fields = {
            "publisher": str(data.get("publisher", "")).strip(),
            "signature_algorithm": str(data.get("signature_algorithm", "")).strip().lower(),
            "public_key": str(data.get("public_key", "")).strip(),
            "signature": str(data.get("signature", "")).strip(),
            "package_sha256": str(data.get("package_sha256", "")).strip().lower(),
        }
        has_signature = any(signature_fields.values())
        if has_signature and (
            not all(signature_fields.values()) or signature_fields["signature_algorithm"] != "ed25519"
        ):
            raise PluginError(
                "Signed plugins require publisher, Ed25519 signature metadata, public_key, "
                "signature, and package_sha256."
            )
        raw_permissions = data.get("permissions", [])
        if not isinstance(raw_permissions, list):
            raise PluginError("Plugin permissions must be a list.")
        permissions = frozenset(str(permission).strip() for permission in raw_permissions)
        unknown = permissions - _ALLOWED_PERMISSIONS
        if unknown:
            raise PluginError(f"Unknown plugin permissions: {sorted(unknown)}")
        return cls(
            plugin_id=plugin_id,
            name=name,
            version=version,
            description=description,
            entrypoint=entrypoint,
            tool_names=tool_names,
            permissions=permissions,
            enabled_by_default=bool(data.get("enabled_by_default", False)),
            trusted=bool(data.get("trusted", False)),
            **signature_fields,
        )

    @property
    def requires_confirmation(self) -> bool:
        return bool(self.permissions & _CONFIRMATION_PERMISSIONS)


@dataclass
class PluginRecord:
    """Runtime state and diagnostics for one discovered plugin."""

    manifest: PluginManifest
    directory: Path
    state: str = "discovered"
    error: str | None = None
    loaded_tool_names: list[str] = field(default_factory=list)
    signature_status: str = "unsigned_local"
    signing_key_fingerprint: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.manifest.plugin_id,
            "name": self.manifest.name,
            "version": self.manifest.version,
            "description": self.manifest.description,
            "state": self.state,
            "tools": list(self.manifest.tool_names),
            "loaded_tools": list(self.loaded_tool_names),
            "permissions": sorted(self.manifest.permissions),
            "requires_confirmation": self.manifest.requires_confirmation,
            "trusted": self.manifest.trusted,
            "enabled_by_default": self.manifest.enabled_by_default,
            "error": self.error,
            "publisher": self.manifest.publisher or None,
            "signature_algorithm": self.manifest.signature_algorithm or None,
            "signature_status": self.signature_status,
            "signing_key_fingerprint": self.signing_key_fingerprint,
        }


class PluginToolAdapter(Tool):
    """Namespace a plugin tool so it cannot collide with core tools."""

    def __init__(self, plugin_id: str, tool: Tool) -> None:
        self._inner = tool
        self.plugin_id = plugin_id
        self.inner_name = tool.name
        self.name = f"plugin.{plugin_id}.{tool.name}"
        self.description = f"[{plugin_id}] {tool.description}"

    async def run(self, **kwargs: Any) -> Any:
        return await self._inner.run(**kwargs)
