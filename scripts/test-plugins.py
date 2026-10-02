"""Phase 4 plugin architecture and API checks."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory


async def main() -> None:
    from app.main import app
    from app.services.plugins import PluginManager, plugin_manager
    from app.services.tools import registry

    bundled = plugin_manager.get("hello_world")
    assert bundled is not None
    assert bundled.state == "enabled"
    assert registry.get("plugin.hello_world.hello_world") is not None

    result = await plugin_manager.execute(
        "hello_world",
        "hello_world",
        {"name": "Aarya"},
        confirmed=False,
    )
    assert result.status == "completed"
    assert result.result["message"] == "Hello, Aarya!"

    disabled = plugin_manager.disable("hello_world")
    assert disabled.state == "disabled"
    assert registry.get("plugin.hello_world.hello_world") is None
    enabled = plugin_manager.enable("hello_world")
    assert enabled.state == "enabled"

    with TemporaryDirectory() as temporary_dir:
        root = Path(temporary_dir)
        invalid = root / "unsafe_plugin"
        invalid.mkdir()
        (invalid / "plugin.json").write_text(
            json.dumps(
                {
                    "id": "unsafe_plugin",
                    "name": "Unsafe",
                    "version": "1.0.0",
                    "description": "Invalid entrypoint test",
                    "entrypoint": "../outside.py:create_plugin",
                    "tools": ["unsafe"],
                    "permissions": [],
                    "enabled_by_default": True,
                    "trusted": True,
                }
            ),
            encoding="utf-8",
        )
        isolated = PluginManager(root)
        isolated.discover()
        assert isolated.get("unsafe_plugin").state == "failed"
        assert "escapes" in (isolated.get("unsafe_plugin").error or "")

        protected = root / "protected_plugin"
        protected.mkdir()
        (protected / "plugin.py").write_text(
            "from app.services.tools.base import Tool\n"
            "class ProtectedTool(Tool):\n"
            "    name = 'protected'\n"
            "    description = 'Protected test tool'\n"
            "    async def run(self):\n"
            "        return {'ok': True}\n"
            "def create_plugin():\n"
            "    return [ProtectedTool()]\n",
            encoding="utf-8",
        )
        (protected / "plugin.json").write_text(
            json.dumps(
                {
                    "id": "protected_plugin",
                    "name": "Protected",
                    "version": "1.0.0",
                    "description": "Protected permission test",
                    "entrypoint": "plugin.py:create_plugin",
                    "tools": ["protected"],
                    "permissions": ["network"],
                    "enabled_by_default": True,
                    "trusted": True,
                }
            ),
            encoding="utf-8",
        )
        isolated.refresh()
        protected_result = await isolated.execute("protected_plugin", "protected", {})
        assert protected_result.status == "confirmation_required"
        isolated.disable("protected_plugin")

    import httpx

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        catalog = await client.get("/api/v1/plugins")
        assert catalog.status_code == 200, catalog.text
        assert any(plugin["id"] == "hello_world" for plugin in catalog.json()["plugins"])

        executed = await client.post(
            "/api/v1/plugins/hello_world/execute",
            json={"tool": "hello_world", "arguments": {"name": "API"}},
        )
        assert executed.status_code == 200, executed.text
        assert executed.json()["status"] == "completed"

        disabled_response = await client.post("/api/v1/plugins/hello_world/disable")
        assert disabled_response.status_code == 200
        reenabled_response = await client.post("/api/v1/plugins/hello_world/enable")
        assert reenabled_response.status_code == 200, reenabled_response.text

    print("plugin architecture checks passed")


if __name__ == "__main__":
    asyncio.run(main())
