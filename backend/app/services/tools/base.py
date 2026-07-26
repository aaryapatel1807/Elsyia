"""
Base Tool Interface

Abstract base class defining the interface for all Elysia tools.
Mirrors the Strategy pattern used by app.services.llm.base.LLMProvider,
so tools and providers compose the same way through the service layer.

NOTE — Phase sequencing: the project roadmap places tool calling in
Phase 3 (after Memory in Phase 2). This module exists now so the
interface is stable and future tools have somewhere to live, but
nothing here is wired into the Phase 1 chat flow
(app/services/chat/conversation.py). Wiring a tool into actual
LLM tool-calling is a deliberate, later decision — not a side effect
of adding a file here.
"""

from abc import ABC, abstractmethod
from typing import Any


class ToolError(Exception):
    """Raised when a tool fails to execute."""


class Tool(ABC):
    """
    Abstract base class for a single callable tool.

    Each tool is self-contained: it declares its own name, description,
    and parameter schema so an LLM provider's tool-calling format can be
    built from a list of Tool instances without per-provider glue code.
    """

    #: Stable identifier used in tool-call requests/responses.
    name: str

    #: Human/LLM-readable description of what the tool does and when to
    #: use it. Kept here (not scattered in prompts) so behavior and
    #: documentation can't drift apart.
    description: str

    @abstractmethod
    async def run(self, **kwargs: Any) -> Any:
        """
        Execute the tool.

        Args:
            **kwargs: Tool-specific arguments, validated by the caller
                against the tool's parameter schema before this is invoked.

        Returns:
            JSON-serializable result to hand back to the LLM.

        Raises:
            ToolError: If execution fails in an expected way (bad input,
                upstream service down, etc.). Unexpected exceptions are
                left to propagate and be logged by the caller.
        """
        raise NotImplementedError
