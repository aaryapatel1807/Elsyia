"""Elsyia MCP client: "build your own with MCP" extensibility.

The Model Context Protocol lets community-built servers expose tools
(filesystem, fetch, databases, Notion, Slack, …) over a standard
interface. Elsyia acts as an MCP *client*: servers the user lists in
``~/.elsyia/mcp.json`` are connected at backend startup (stdio or SSE
transports), and each server's tools are bridged into Elsyia's own tool
registry as ``mcp.<server>.<tool>`` — visible to the agent-mode planner
and callable by the executor with output threading, exactly like
built-in tools.

Resilience rules (a community server must never break Elsyia):
- Connections happen in a background task at startup; a dead, slow, or
  misconfigured server is marked unavailable and skipped — Elsyia keeps
  working with whatever is left.
- Tool calls to an unavailable server re-attempt one connection, then
  fail cleanly with a plain-English error.
- Only servers listed in the user's own config file ever run. The
  config file is the trust boundary: Elsyia never downloads, installs, or
  launches an MCP server on its own.

Confirmation policy: outward-acting MCP tools (anything that writes,
sends, deletes, or executes) are confirmation-gated through the same
registry policy as built-ins; read-only tools run silently. The
per-server ``confirm`` setting (``outward``/``all``/``none``) can
tighten or loosen this — ``none`` is documented as dangerous.
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import sys
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core import get_logger, get_settings
from app.services.elsyia.paths import elsyia_data_dir
from app.services.tools.base import Tool, ToolError
from app.services.tools.registry import registry

logger = get_logger("elsyia.mcp")

CONFIG_NAME = "mcp.json"

# Tool names containing one of these verbs act on the outside world and
# are confirmation-gated unless the server config says otherwise.
_OUTWARD_RE = re.compile(
    r"(write|create|send|delete|remove|update|edit|post|put|push|"
    r"execute|run|launch|insert|append|move|rename|mkdir|publish|call)_?",
    re.IGNORECASE,
)

_NAME_CLEAN_RE = re.compile(r"[^a-z0-9]+")


def sanitize_name(raw: str) -> str:
    """Make a registry-safe lowercase name fragment."""
    cleaned = _NAME_CLEAN_RE.sub("_", (raw or "").lower()).strip("_")
    return cleaned or "server"


@dataclass
class MCPServerConfig:
    """One user-configured MCP server."""

    name: str
    transport: str = "stdio"  # "stdio" | "sse"
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    cwd: str = ""
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    confirm: str = "outward"  # "outward" | "all" | "none"

    @classmethod
    def from_dict(cls, name: str, raw: dict[str, Any]) -> "MCPServerConfig":
        raw = raw or {}
        return cls(
            name=name,
            transport=str(raw.get("transport", "stdio")).lower(),
            command=str(raw.get("command", "")),
            args=[str(a) for a in (raw.get("args") or [])],
            env={str(k): str(v) for k, v in (raw.get("env") or {}).items()},
            cwd=str(raw.get("cwd", "")),
            url=str(raw.get("url", "")),
            headers={str(k): str(v) for k, v in (raw.get("headers") or {}).items()},
            enabled=bool(raw.get("enabled", True)),
            confirm=str(raw.get("confirm", "outward")).lower(),
        )


def mcp_config_path() -> Path:
    """Path to the user's MCP server config (the trust boundary)."""
    raw = getattr(get_settings(), "ELSYIA_MCP_CONFIG", "~/.elsyia/mcp.json")
    return Path(str(raw)).expanduser()


def load_mcp_config() -> dict[str, MCPServerConfig]:
    """Read user-configured servers. Missing/invalid file -> {} (never raises)."""
    path = mcp_config_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Ignoring unreadable MCP config %s: %s", path, exc)
        return {}
    servers = (raw or {}).get("servers") or {}
    configs: dict[str, MCPServerConfig] = {}
    for name, entry in servers.items():
        if not isinstance(entry, dict):
            continue
        safe = sanitize_name(str(name))
        if safe in configs:
            continue
        configs[safe] = MCPServerConfig.from_dict(safe, entry)
    return configs


def _resolve_command(command: str) -> str:
    """Resolve a bare server command: PATH first, then the venv's bin dir."""
    if not command:
        return command
    if "/" in command or "\\" in command:
        return command
    found = shutil.which(command)
    if found:
        return found
    venv_bin = Path(sys.executable).parent / command
    if venv_bin.exists():
        return str(venv_bin)
    return command  # let the spawn fail with a clear error later


def _compact_args(schema: dict[str, Any]) -> str:
    """Render a JSON schema as a planner-friendly arg hint: {path: string*, q: integer}."""
    if not isinstance(schema, dict):
        return ""
    props = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    parts = []
    for pname, pspec in list(props.items())[:12]:
        ptype = pspec.get("type", "any") if isinstance(pspec, dict) else "any"
        star = "*" if pname in required else ""
        parts.append(f"{pname}: {ptype}{star}")
    if not parts:
        return ""
    return "Args: {" + ", ".join(parts) + "}  (* = required)"


def _tool_needs_confirm(server_cfg: MCPServerConfig, tool_name: str, annotations: Any) -> bool:
    """Decide the confirmation gate for one MCP tool."""
    mode = (server_cfg.confirm or "outward").lower()
    if mode == "all":
        return True
    if mode == "none":
        return False
    # MCP tool annotations, when the server provides them, beat the heuristic.
    try:
        if annotations is not None:
            if getattr(annotations, "destructiveHint", None) is True:
                return True
            if getattr(annotations, "readOnlyHint", None) is True:
                return False
    except Exception:  # noqa: BLE001 - annotations are best-effort
        pass
    return bool(_OUTWARD_RE.search(tool_name or ""))


def _result_to_json(result: Any) -> Any:
    """Convert an MCP CallToolResult into JSON-serializable data."""
    content = getattr(result, "content", None)
    if content is None:
        return result
    texts: list[str] = []
    structured: list[Any] = []
    for block in content:
        btype = getattr(block, "type", "")
        if btype == "text":
            texts.append(getattr(block, "text", ""))
        else:
            try:
                structured.append(block.model_dump())
            except Exception:  # noqa: BLE001
                structured.append(str(block))
    if structured and not texts:
        return structured[0] if len(structured) == 1 else structured
    joined = "\n".join(texts)
    if structured:
        return {"text": joined, "attachments": structured}
    # Prefer parsed JSON when the server returned it.
    try:
        return json.loads(joined)
    except (json.JSONDecodeError, ValueError):
        return joined


class MCPToolError(ToolError):
    """An MCP tool call failed in an expected way (server down, bad args)."""


class MCPTool(Tool):
    """One MCP server tool, bridged into Elsyia's registry as mcp.<server>.<tool>."""

    def __init__(
        self,
        manager: "MCPManager",
        server: str,
        tool_name: str,
        description: str,
        input_schema: dict[str, Any],
    ) -> None:
        self._manager = manager
        self._server = server
        self._tool_name = tool_name
        self.name = f"mcp.{server}.{sanitize_name(tool_name)}"
        hint = _compact_args(input_schema)
        self.description = (description or "MCP tool").strip()
        if hint:
            self.description = f"{self.description}  [{hint}]"
        self.description += f"  (via MCP server '{server}')"

    async def run(self, **kwargs: Any) -> Any:
        return await self._manager.call_tool(self._server, self._tool_name, kwargs)


class MCPManager:
    """Owns MCP server connections and bridges their tools into the registry."""

    def __init__(self) -> None:
        self._configs: dict[str, MCPServerConfig] = {}
        self._stacks: dict[str, AsyncExitStack] = {}
        self._sessions: dict[str, Any] = {}
        self._registered: dict[str, list[str]] = {}
        self._errors: dict[str, str] = {}
        self._lock = asyncio.Lock()
        self._started = False

    # -- lifecycle ----------------------------------------------------

    def startup(self) -> None:
        """Schedule background connection; never blocks or raises."""
        if self._started:
            return
        self._started = True
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning("No running loop for MCP startup; servers stay lazy.")
            return
        loop.create_task(self._connect_all(), name="elsyia-mcp-connect")

    async def aclose(self) -> None:
        """Close every open MCP session (best-effort)."""
        async with self._lock:
            for name, stack in list(self._stacks.items()):
                try:
                    await stack.aclose()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Error closing MCP server %s: %s", name, exc)
            self._stacks.clear()
            self._sessions.clear()

    # -- connection ---------------------------------------------------

    def _open_session(self, cfg: MCPServerConfig) -> Any:
        """Return an async CM yielding a connected ClientSession. Sealed for tests."""
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.sse import sse_client
        from mcp.client.stdio import stdio_client

        class _SessionCM:
            def __init__(self, mgr: "MCPManager", cfg: MCPServerConfig) -> None:
                self._mgr = mgr
                self._cfg = cfg
                self._stack = AsyncExitStack()

            async def __aenter__(self) -> Any:
                if self._cfg.transport == "sse":
                    read, write = await self._stack.enter_async_context(
                        sse_client(self._cfg.url, headers=self._cfg.headers or None)
                    )
                else:
                    params = StdioServerParameters(
                        command=_resolve_command(self._cfg.command),
                        args=list(self._cfg.args),
                        env=dict(self._cfg.env) or None,
                        cwd=self._cfg.cwd or None,
                    )
                    read, write = await self._stack.enter_async_context(
                        stdio_client(params)
                    )
                session = await self._stack.enter_async_context(
                    ClientSession(read, write)
                )
                await session.initialize()
                self._mgr._stacks[self._cfg.name] = self._stack
                return session

            async def __aexit__(self, *exc: Any) -> None:
                await self._stack.aclose()
                self._mgr._stacks.pop(self._cfg.name, None)

        return _SessionCM(self, cfg)

    async def _connect_server(self, name: str) -> bool:
        """Connect one server and register its tools. Returns True on success."""
        cfg = self._configs.get(name)
        if cfg is None or not cfg.enabled:
            return False
        if cfg.transport == "sse" and not cfg.url:
            self._errors[name] = "SSE server has no url configured"
            return False
        if cfg.transport == "stdio" and not cfg.command:
            self._errors[name] = "stdio server has no command configured"
            return False
        try:
            session = await self._open_session(cfg).__aenter__()
        except Exception as exc:  # noqa: BLE001 - a dead server must not break Elsyia
            self._errors[name] = f"{type(exc).__name__}: {exc}"
            logger.warning("MCP server '%s' unavailable: %s", name, self._errors[name])
            return False
        try:
            listed = await session.list_tools()
        except Exception as exc:  # noqa: BLE001
            self._errors[name] = f"list_tools failed: {type(exc).__name__}: {exc}"
            logger.warning("MCP server '%s' %s", name, self._errors[name])
            return False
        async with self._lock:
            self._sessions[name] = session
            self._errors.pop(name, None)
            self._unregister_server_tools(name)
            registered: list[str] = []
            for mcp_tool in listed.tools or []:
                tool = MCPTool(
                    self,
                    name,
                    mcp_tool.name,
                    mcp_tool.description or "",
                    mcp_tool.inputSchema or {},
                )
                if registry.get(tool.name) is not None:
                    continue
                registry.register(
                    tool,
                    confirmation_required=_tool_needs_confirm(
                        cfg, mcp_tool.name, getattr(mcp_tool, "annotations", None)
                    ),
                )
                registered.append(tool.name)
            self._registered[name] = registered
        logger.info("MCP server '%s' connected: %d tools", name, len(registered))
        return True

    def _unregister_server_tools(self, name: str) -> None:
        for tool_name in self._registered.pop(name, []):
            registry.unregister(tool_name)

    async def _connect_all(self) -> None:
        """Connect every enabled server; individual failures are contained."""
        self._configs = load_mcp_config()
        if not getattr(get_settings(), "ELSYIA_MCP_ENABLED", True):
            logger.info("MCP disabled via ELSYIA_MCP_ENABLED; skipping.")
            return
        for name, cfg in self._configs.items():
            if cfg.enabled:
                await self._connect_server(name)

    async def refresh(self) -> None:
        """Reconnect everything (used by POST /elsyia/mcp/refresh)."""
        await self.aclose()
        async with self._lock:
            for name in list(self._registered):
                self._unregister_server_tools(name)
            self._errors.clear()
        self._configs = load_mcp_config()
        await self._connect_all()

    # -- tool calls ---------------------------------------------------

    async def call_tool(self, server: str, tool: str, args: dict[str, Any]) -> Any:
        """Call one MCP tool, reconnecting once if the session is gone."""
        session = self._sessions.get(server)
        if session is None:
            ok = await self._connect_server(server)
            session = self._sessions.get(server) if ok else None
        if session is None:
            raise MCPToolError(
                f"MCP server '{server}' is unavailable: "
                f"{self._errors.get(server, 'not configured')}"
            )
        try:
            result = await session.call_tool(tool, args or {})
        except Exception as exc:  # noqa: BLE001
            raise MCPToolError(f"MCP call {server}.{tool} failed: {exc}") from exc
        if getattr(result, "isError", False):
            raise MCPToolError(
                f"MCP tool {server}.{tool} reported an error: "
                f"{_result_to_json(result)}"
            )
        return _result_to_json(result)

    # -- status -------------------------------------------------------

    def status(self) -> dict[str, Any]:
        """Per-server MCP status for GET /elsyia/mcp/status."""
        servers: dict[str, Any] = {}
        for name, cfg in self._configs.items():
            servers[name] = {
                "transport": cfg.transport,
                "enabled": cfg.enabled,
                "available": name in self._sessions,
                "tools": len(self._registered.get(name, [])),
                "confirm_policy": cfg.confirm,
                "error": self._errors.get(name),
            }
        return {
            "enabled": bool(getattr(get_settings(), "ELSYIA_MCP_ENABLED", True)),
            "config": str(mcp_config_path()),
            "servers": servers,
        }

    def summary(self) -> dict[str, Any]:
        """Compact MCP summary for GET /elsyia/status."""
        st = self.status()
        return {
            "enabled": st["enabled"],
            "servers": len(st["servers"]),
            "available": sum(1 for s in st["servers"].values() if s["available"]),
            "tools": sum(s["tools"] for s in st["servers"].values()),
        }


_manager: MCPManager | None = None


def get_mcp_manager() -> MCPManager:
    """Process-wide MCP manager singleton."""
    global _manager
    if _manager is None:
        _manager = MCPManager()
    return _manager


def reset_mcp_manager() -> None:
    """Drop the singleton (tests only)."""
    global _manager
    _manager = None
