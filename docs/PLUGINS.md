# Elysia Phase 4 Plugins

Phase 4 introduces a **trusted local plugin architecture** for extending Elysia without modifying the core tool modules. Plugins are installed as directories under the repository `plugins/` folder and must contain a `plugin.json` manifest plus a Python entrypoint.

This phase intentionally does not download or execute arbitrary marketplace code. A future marketplace must add package signing, review, and a stronger operating-system sandbox before third-party code can be trusted automatically.

## Manifest

```json
{
  "id": "hello_world",
  "name": "Hello World",
  "version": "1.0.0",
  "description": "A minimal example plugin.",
  "entrypoint": "plugin.py:create_plugin",
  "tools": ["hello_world"],
  "permissions": [],
  "enabled_by_default": true,
  "trusted": true
}
```

The `id` is lowercase and stable. The entrypoint must resolve to a file inside the plugin directory. Supported permissions are `read_local_files`, `write_local_files`, `network`, `launch_application`, and `notifications`.

## Trust and safety model

A plugin is loaded only when its manifest is valid, its entrypoint stays within its own plugin directory, and it is explicitly marked trusted. Plugin tools are registered under the namespace `plugin.<plugin_id>.<tool_name>` to prevent collisions with core tools.

Permissions are declarative and visible through the plugin catalog. Plugins requesting `write_local_files`, `network`, `launch_application`, or `notifications` require confirmation before execution. Plugin execution is bounded by a timeout and failures are contained so they do not crash the backend. This is process-level and registry-level isolation, not a complete OS sandbox; arbitrary third-party plugin installation remains disabled by design.

## Lifecycle

Plugins move through `discovered`, `enabled`, `disabled`, `blocked`, and `failed` states. The backend discovers manifests at startup, loads only trusted manifests marked `enabled_by_default`, and exposes explicit enable/disable controls. Disabling a plugin unregisters its tools without deleting user files.

## API

```http
GET /api/v1/plugins
```

```http
POST /api/v1/plugins/refresh
```

Rediscover local manifests and reload trusted default plugins without restarting the backend.

```http
POST /api/v1/plugins/{plugin_id}/enable
Content-Type: application/json

{"confirmed": false}
```

```http
POST /api/v1/plugins/{plugin_id}/disable
```

```http
POST /api/v1/plugins/{plugin_id}/execute
Content-Type: application/json

{"tool":"hello_world","arguments":{"name":"Aarya"},"confirmed":false}
```

Plugin execution is also visible in the existing local tool audit log. Sensitive arguments are redacted by the same audit policy used by Phase 3 tools. Marketplace downloads, arbitrary installation, and automatic execution of untrusted code are intentionally outside this phase until package signing and a stronger process/OS sandbox are available.

## SDK shape

A plugin entrypoint exposes a `create_plugin()` function returning one or more existing `Tool` instances:

```python
from app.services.tools.base import Tool

class HelloWorldTool(Tool):
    name = "hello_world"
    description = "Return a greeting."

    async def run(self, name: str = "there") -> dict:
        return {"message": f"Hello, {name}!"}


def create_plugin() -> list[Tool]:
    return [HelloWorldTool()]
```

The plugin directory is local and user-owned. Keep secrets out of manifests and plugin source files. Plugins should use explicit permission declarations and should not perform network, filesystem writes, or desktop actions unless the manifest requests the corresponding permission.
