"""Bundled Phase 4 example plugin."""

from __future__ import annotations

from app.services.tools.base import Tool


class HelloWorldTool(Tool):
    name = "hello_world"
    description = "Return a local greeting from the bundled example plugin."

    async def run(self, name: str = "there") -> dict[str, str]:
        cleaned = " ".join(name.strip().split())[:80] or "there"
        return {"message": f"Hello, {cleaned}!"}


def create_plugin() -> list[Tool]:
    return [HelloWorldTool()]
