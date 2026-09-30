"""Local plugin discovery and lifecycle manager."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

from app.core import get_settings
from app.services.plugins.base import PluginError, PluginManifest, PluginRecord, PluginToolAdapter
from app.services.plugins.signing import PluginSignatureError, verify_manifest_signature
from app.services.tools.base import Tool
from app.services.tools.registry import ToolExecutionResult, registry


class PluginManager:
    """Discover and execute explicitly trusted local plugins."""

    def __init__(self, plugin_root: str | Path | None = None) -> None:
        self.plugin_root = (
            Path(plugin_root).resolve()
            if plugin_root
            else Path(__file__).parents[4].joinpath("plugins").resolve()
        )
        self._records: dict[str, PluginRecord] = {}
        self._discovery_errors: list[dict[str, str]] = []

    def discover(self, *, auto_enable: bool = True) -> None:
        """Read manifests and optionally enable trusted default plugins."""
        self._records.clear()
        self._discovery_errors.clear()
        if not self.plugin_root.exists():
            return
        try:
            candidates = sorted(path for path in self.plugin_root.iterdir() if path.is_dir())
        except OSError as exc:
            self._discovery_errors.append({"path": str(self.plugin_root), "error": str(exc)})
            return
        for directory in candidates:
            manifest_path = directory / "plugin.json"
            if not manifest_path.is_file():
                continue
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest = PluginManifest.from_dict(data)
                if manifest.plugin_id in self._records:
                    raise PluginError(f"Duplicate plugin id: {manifest.plugin_id}")
                record = PluginRecord(manifest=manifest, directory=directory)
                if manifest.signature:
                    try:
                        trusted_keys = {
                            item.strip().lower()
                            for item in get_settings().PLUGIN_TRUSTED_KEY_FINGERPRINTS.split(";")
                            if item.strip()
                        }
                        record.signing_key_fingerprint = verify_manifest_signature(
                            data, directory, trusted_keys
                        )
                        record.signature_status = "verified"
                    except (OSError, PluginSignatureError) as exc:
                        record.state = "failed"
                        record.error = str(exc)
                        record.signature_status = "invalid"
                self._records[manifest.plugin_id] = record
            except (OSError, json.JSONDecodeError, PluginError) as exc:
                self._discovery_errors.append({"path": str(manifest_path), "error": str(exc)})
        if auto_enable:
            for plugin_id, record in list(self._records.items()):
                if record.manifest.enabled_by_default:
                    try:
                        self.enable(plugin_id)
                    except PluginError:
                        # The record retains a failed/blocked state for diagnostics.
                        continue

    def refresh(self, *, auto_enable: bool = True) -> None:
        """Reload local manifests and entrypoints without restarting the backend."""
        for plugin_id, record in list(self._records.items()):
            if record.state == "enabled":
                self.disable(plugin_id)
        self.discover(auto_enable=auto_enable)

    def list(self) -> list[dict[str, Any]]:
        """Return plugin metadata without source code or private arguments."""
        plugins = [record.as_dict() for record in self._records.values()]
        plugins.extend(
            {
                "id": "invalid",
                "name": "Invalid plugin",
                "version": "",
                "description": "Manifest rejected",
                "state": "failed",
                "tools": [],
                "loaded_tools": [],
                "permissions": [],
                "requires_confirmation": False,
                "trusted": False,
                "enabled_by_default": False,
                "error": error["error"],
                "path": error["path"],
            }
            for error in self._discovery_errors
        )
        return plugins

    def get(self, plugin_id: str) -> PluginRecord | None:
        return self._records.get(plugin_id)

    def _entrypoint_path(self, record: PluginRecord) -> tuple[Path, str]:
        module_name, function_name = record.manifest.entrypoint.split(":", 1)
        module_path = (record.directory / module_name).resolve()
        try:
            module_path.relative_to(record.directory.resolve())
        except ValueError as exc:
            raise PluginError("Plugin entrypoint escapes its plugin directory.") from exc
        if not module_path.is_file():
            raise PluginError("Plugin entrypoint file does not exist.")
        return module_path, function_name

    def _load_tools(self, record: PluginRecord) -> list[Tool]:
        module_path, function_name = self._entrypoint_path(record)
        module_key = f"elysia_plugin_{record.manifest.plugin_id}"
        spec = importlib.util.spec_from_file_location(module_key, module_path)
        if spec is None or spec.loader is None:
            raise PluginError("Could not create a plugin module loader.")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_key] = module
        try:
            spec.loader.exec_module(module)
        except Exception as exc:
            sys.modules.pop(module_key, None)
            raise PluginError(f"Plugin import failed: {type(exc).__name__}") from exc
        factory = getattr(module, function_name, None)
        if not callable(factory):
            raise PluginError("Plugin entrypoint function was not found.")
        try:
            raw_tools = factory()
        except Exception as exc:
            raise PluginError(f"Plugin factory failed: {type(exc).__name__}") from exc
        tools = raw_tools if isinstance(raw_tools, list) else [raw_tools]
        if not tools or any(not isinstance(tool, Tool) for tool in tools):
            raise PluginError("Plugin factory must return Tool instances.")
        declared = set(record.manifest.tool_names)
        actual = {tool.name for tool in tools}
        if actual != declared:
            raise PluginError("Plugin manifest tools do not match the entrypoint tools.")
        return tools

    def enable(self, plugin_id: str) -> PluginRecord:
        record = self.get(plugin_id)
        if record is None:
            raise PluginError(f"Unknown plugin: {plugin_id}")
        if not record.manifest.trusted:
            record.state = "blocked"
            record.error = "Plugin is not marked trusted."
            raise PluginError(record.error)
        if record.signature_status == "invalid":
            raise PluginError(record.error or "Plugin signature verification failed.")
        if record.state == "enabled":
            return record
        try:
            tools = self._load_tools(record)
            adapters = [PluginToolAdapter(plugin_id, tool) for tool in tools]
            for adapter in adapters:
                registry.register(
                    adapter,
                    confirmation_required=record.manifest.requires_confirmation,
                )
            record.loaded_tool_names = [adapter.name for adapter in adapters]
            record.state = "enabled"
            record.error = None
            return record
        except Exception as exc:
            record.state = "failed"
            record.error = str(exc)
            raise PluginError(record.error) from exc

    def disable(self, plugin_id: str) -> PluginRecord:
        record = self.get(plugin_id)
        if record is None:
            raise PluginError(f"Unknown plugin: {plugin_id}")
        for tool_name in record.loaded_tool_names:
            registry.unregister(tool_name)
        record.loaded_tool_names.clear()
        record.state = "disabled"
        record.error = None
        return record

    async def execute(
        self,
        plugin_id: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        *,
        confirmed: bool = False,
    ) -> ToolExecutionResult:
        record = self.get(plugin_id)
        if record is None:
            return ToolExecutionResult(status="failed", tool_name=tool_name, error="Unknown plugin.")
        if record.state != "enabled":
            return ToolExecutionResult(
                status="failed",
                tool_name=tool_name,
                error=f"Plugin is not enabled (state: {record.state}).",
            )
        if tool_name not in record.manifest.tool_names:
            return ToolExecutionResult(status="failed", tool_name=tool_name, error="Unknown plugin tool.")
        namespaced = f"plugin.{plugin_id}.{tool_name}"
        return await registry.execute(namespaced, arguments, confirmed=confirmed)


plugin_manager = PluginManager()
plugin_manager.discover(auto_enable=True)
