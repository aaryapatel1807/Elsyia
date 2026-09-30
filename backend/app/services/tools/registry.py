"""Tool registry and permission-aware execution service."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.services.tools.base import Tool, ToolError


@dataclass(frozen=True)
class ToolExecutionResult:
    """Structured result returned by a tool execution attempt."""

    status: str
    tool_name: str
    result: Any = None
    error: str | None = None
    confirmation_required: bool = False
    confirmation_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class ToolRegistry:
    """Registry for tools exposed to the assistant."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}
        self._confirmation_required: set[str] = set()

    def register(self, tool: Tool, *, confirmation_required: bool = False) -> None:
        """Register one tool and its permission policy."""
        if not getattr(tool, "name", "") or not getattr(tool, "description", ""):
            raise ValueError("Tools must define name and description")
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool
        if confirmation_required:
            self._confirmation_required.add(tool.name)

    def get(self, name: str) -> Tool | None:
        """Return a registered tool by stable name."""
        return self._tools.get(name)

    def unregister(self, name: str) -> bool:
        """Remove a tool registration, used when disabling a plugin."""
        removed = self._tools.pop(name, None)
        self._confirmation_required.discard(name)
        return removed is not None

    def list(self) -> list[dict[str, Any]]:
        """Return tool metadata for diagnostics and future model tool schemas."""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "confirmation_required": tool.name in self._confirmation_required,
            }
            for tool in self._tools.values()
        ]

    async def execute(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        *,
        confirmed: bool = False,
    ) -> ToolExecutionResult:
        """Execute a tool after enforcing registration and confirmation policy."""
        tool = self.get(name)
        if tool is None:
            return ToolExecutionResult(
                status="failed",
                tool_name=name,
                error=f"Unknown tool: {name}",
            )

        if name in self._confirmation_required and not confirmed:
            return ToolExecutionResult(
                status="confirmation_required",
                tool_name=name,
                confirmation_required=True,
                confirmation_message=f"Confirm that Elysia should run {name}.",
            )

        try:
            result = await tool.run(**(arguments or {}))
            return ToolExecutionResult(status="completed", tool_name=name, result=result)
        except ToolError as exc:
            return ToolExecutionResult(status="failed", tool_name=name, error=str(exc))
        except Exception as exc:
            return ToolExecutionResult(
                status="failed",
                tool_name=name,
                error="Tool execution failed unexpectedly.",
                metadata={"exception": type(exc).__name__},
            )


registry = ToolRegistry()
