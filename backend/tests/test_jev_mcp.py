"""Tests for the Jev MCP client.

Real MCP servers are faked at the transport seam (``MCPManager._open_session``)
— no subprocesses, no network. The bridging logic (config parsing, tool
listing -> namespaced registration, call bridging, confirm-gating, dead-server
degradation) is exercised for real. End-to-end verification against genuine
community servers (sqlite, filesystem) was done separately during development.
"""

import json

import pytest

from app.services.jev import mcp_client
from app.services.jev.mcp_client import (
    MCPManager,
    MCPServerConfig,
    MCPTool,
    MCPToolError,
    _compact_args,
    _resolve_command,
    _tool_needs_confirm,
    load_mcp_config,
    sanitize_name,
)
from app.services.tools.registry import registry


# ---------------------------------------------------------------- fakes


class _FakeAnnotations:
    def __init__(self, destructive=None, read_only=None):
        self.destructiveHint = destructive
        self.readOnlyHint = read_only


class _FakeMCPToolDef:
    def __init__(self, name, description="", schema=None, annotations=None):
        self.name = name
        self.description = description
        self.inputSchema = schema or {"type": "object", "properties": {}}
        self.annotations = annotations


class _FakeText:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _FakeCallResult:
    def __init__(self, content, isError=False):
        self.content = content
        self.isError = isError


class _FakeSession:
    def __init__(self, tools, error_tools=None):
        self._tools = tools
        self._error_tools = error_tools or {}
        self.calls = []

    async def list_tools(self):
        class _R:
            pass

        r = _R()
        r.tools = self._tools
        return r

    async def call_tool(self, name, args):
        self.calls.append((name, args))
        if name in self._error_tools:
            return _FakeCallResult([_FakeText(self._error_tools[name])], isError=True)
        return _FakeCallResult(
            [_FakeText(json.dumps({"ok": True, "tool": name, "args": args}))]
        )


class _FakeCM:
    """Stands in for MCPManager._open_session's async context manager."""

    def __init__(self, session=None, exc=None):
        self._session = session
        self._exc = exc

    async def __aenter__(self):
        if self._exc is not None:
            raise self._exc
        return self._session

    async def __aexit__(self, *args):
        return None


@pytest.fixture
def manager():
    m = MCPManager()
    yield m


@pytest.fixture(autouse=True)
def clean_mcp_tools():
    """Whatever the test registers under mcp.* is removed afterwards."""
    yield
    for name in [n for n in list(registry._tools) if n.startswith("mcp.")]:
        registry.unregister(name)


def _patch_open(monkeypatch, manager, session=None, exc=None):
    monkeypatch.setattr(
        MCPManager, "_open_session", lambda self, cfg: _FakeCM(session, exc)
    )


# ---------------------------------------------------------------- units


def test_sanitize_name():
    assert sanitize_name("My Server!") == "my_server"
    assert sanitize_name("filesystem") == "filesystem"
    assert sanitize_name("") == "server"
    assert sanitize_name("a.b/c") == "a_b_c"


def test_compact_args():
    schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "limit": {"type": "integer"},
        },
        "required": ["path"],
    }
    hint = _compact_args(schema)
    assert "path: string*" in hint
    assert "limit: integer" in hint
    assert _compact_args({}) == ""
    assert _compact_args(None) == ""


def test_confirm_heuristic():
    cfg = MCPServerConfig(name="s", confirm="outward")
    assert _tool_needs_confirm(cfg, "write_file", None) is True
    assert _tool_needs_confirm(cfg, "send_email", None) is True
    assert _tool_needs_confirm(cfg, "delete_table", None) is True
    assert _tool_needs_confirm(cfg, "read_text_file", None) is False
    assert _tool_needs_confirm(cfg, "list_tables", None) is False
    # MCP annotations beat the heuristic both ways.
    assert (
        _tool_needs_confirm(cfg, "read_text_file", _FakeAnnotations(destructive=True))
        is True
    )
    assert (
        _tool_needs_confirm(cfg, "write_file", _FakeAnnotations(read_only=True))
        is False
    )
    # Per-server overrides.
    assert _tool_needs_confirm(MCPServerConfig(name="s", confirm="all"), "read_x", None)
    assert not _tool_needs_confirm(
        MCPServerConfig(name="s", confirm="none"), "delete_x", None
    )


def test_resolve_command_keeps_paths_and_missing():
    assert _resolve_command("/usr/bin/foo") == "/usr/bin/foo"
    assert _resolve_command("definitely-not-a-real-binary-xyz") == (
        "definitely-not-a-real-binary-xyz"
    )
    assert _resolve_command("") == ""


def test_load_mcp_config_missing_and_invalid(tmp_path, monkeypatch):
    monkeypatch.setattr(
        mcp_client, "mcp_config_path", lambda: tmp_path / "nope.json"
    )
    assert load_mcp_config() == {}
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(mcp_client, "mcp_config_path", lambda: bad)
    assert load_mcp_config() == {}


def test_load_mcp_config_parses(tmp_path, monkeypatch):
    cfg_file = tmp_path / "mcp.json"
    cfg_file.write_text(
        json.dumps(
            {
                "servers": {
                    "sqlite": {
                        "transport": "stdio",
                        "command": "mcp-server-sqlite",
                        "args": ["--db-path", "/tmp/x.db"],
                        "confirm": "outward",
                    },
                    "remote": {
                        "transport": "sse",
                        "url": "http://localhost:8001/sse",
                        "enabled": False,
                    },
                    "broken": "not-a-dict",
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(mcp_client, "mcp_config_path", lambda: cfg_file)
    configs = load_mcp_config()
    assert set(configs) == {"sqlite", "remote"}
    assert configs["sqlite"].command == "mcp-server-sqlite"
    assert configs["sqlite"].args == ["--db-path", "/tmp/x.db"]
    assert configs["remote"].transport == "sse"
    assert configs["remote"].enabled is False


# ---------------------------------------------------------------- bridging


async def test_connect_registers_namespaced_tools(manager, monkeypatch):
    session = _FakeSession(
        [
            _FakeMCPToolDef("read_text_file", "Read a file", {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}),
            _FakeMCPToolDef("write_file", "Write a file"),
        ]
    )
    _patch_open(monkeypatch, manager, session=session)
    manager._configs = {"fs": MCPServerConfig(name="fs", command="dummy-server")}
    assert await manager._connect_server("fs") is True

    read_tool = registry.get("mcp.fs.read_text_file")
    write_tool = registry.get("mcp.fs.write_file")
    assert read_tool is not None and write_tool is not None
    assert isinstance(read_tool, MCPTool)
    # The planner sees the arg schema in the description.
    assert "path: string*" in read_tool.description
    assert "via MCP server 'fs'" in read_tool.description
    # Confirm policy: reads silent, writes gated.
    assert "mcp.fs.read_text_file" not in registry._confirmation_required
    assert "mcp.fs.write_file" in registry._confirmation_required

    status = manager.status()
    assert status["servers"]["fs"]["available"] is True
    assert status["servers"]["fs"]["tools"] == 2
    assert manager.summary()["tools"] == 2


async def test_call_tool_bridges_and_threads_output(manager, monkeypatch):
    session = _FakeSession([_FakeMCPToolDef("read_query", "Run a query")])
    _patch_open(monkeypatch, manager, session=session)
    manager._configs = {"db": MCPServerConfig(name="db", command="dummy-server")}
    await manager._connect_server("db")

    tool = registry.get("mcp.db.read_query")
    result = await tool.run(query="SELECT 1")
    assert result == {"ok": True, "tool": "read_query", "args": {"query": "SELECT 1"}}
    assert session.calls == [("read_query", {"query": "SELECT 1"})]


async def test_registry_execute_applies_confirm_gate(manager, monkeypatch):
    session = _FakeSession([_FakeMCPToolDef("delete_table", "Delete a table")])
    _patch_open(monkeypatch, manager, session=session)
    manager._configs = {"db": MCPServerConfig(name="db", command="dummy-server")}
    await manager._connect_server("db")

    gated = await registry.execute("mcp.db.delete_table", {"name": "t"})
    assert gated.status == "confirmation_required"
    assert gated.confirmation_required is True
    assert session.calls == []  # nothing ran before confirmation

    allowed = await registry.execute(
        "mcp.db.delete_table", {"name": "t"}, confirmed=True
    )
    assert allowed.status == "completed"
    assert session.calls == [("delete_table", {"name": "t"})]


async def test_dead_server_degrades_gracefully(manager, monkeypatch):
    _patch_open(monkeypatch, manager, exc=ConnectionRefusedError("nope"))
    manager._configs = {"ghost": MCPServerConfig(name="ghost", command="dummy-server")}
    # Must not raise: a dead server never breaks Jev.
    assert await manager._connect_server("ghost") is False
    assert "ghost" not in manager._sessions
    assert manager.status()["servers"]["ghost"]["available"] is False
    assert "ConnectionRefusedError" in manager.status()["servers"]["ghost"]["error"]
    assert not [n for n in registry._tools if n.startswith("mcp.")]


async def test_call_on_unavailable_server_raises_cleanly(manager, monkeypatch):
    _patch_open(monkeypatch, manager, exc=OSError("down"))
    manager._configs = {"ghost": MCPServerConfig(name="ghost", command="dummy-server")}
    with pytest.raises(MCPToolError, match="unavailable"):
        await manager.call_tool("ghost", "anything", {})


async def test_tool_error_from_server_becomes_mcp_tool_error(manager, monkeypatch):
    session = _FakeSession(
        [_FakeMCPToolDef("read_query", "x")],
        error_tools={"read_query": "syntax error near FOO"},
    )
    _patch_open(monkeypatch, manager, session=session)
    manager._configs = {"db": MCPServerConfig(name="db", command="dummy-server")}
    await manager._connect_server("db")
    with pytest.raises(MCPToolError, match="syntax error"):
        await manager.call_tool("db", "read_query", {"query": "FOO"})


async def test_disabled_server_is_skipped(manager, monkeypatch):
    session = _FakeSession([_FakeMCPToolDef("read_x", "x")])
    _patch_open(monkeypatch, manager, session=session)
    manager._configs = {"db": MCPServerConfig(name="db", command="dummy-server", enabled=False)}
    assert await manager._connect_server("db") is False
    assert registry.get("mcp.db.read_x") is None


async def test_result_text_passthrough_when_not_json(manager, monkeypatch):
    class _PlainSession(_FakeSession):
        async def call_tool(self, name, args):
            self.calls.append((name, args))
            return _FakeCallResult([_FakeText("just some text")])

    session = _PlainSession([_FakeMCPToolDef("echo_tool", "x")])
    _patch_open(monkeypatch, manager, session=session)
    manager._configs = {"s": MCPServerConfig(name="s", command="dummy-server")}
    await manager._connect_server("s")
    tool = registry.get("mcp.s.echo_tool")
    assert await tool.run() == "just some text"
