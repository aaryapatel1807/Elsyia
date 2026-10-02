"""Phase 7 read-only repository analysis tools."""

from __future__ import annotations

from typing import Any

from app.services.code import CodePolicyError, repository_indexer
from app.services.tools.base import Tool, ToolError


class IndexCodeRepositoryTool(Tool):
    name = "index_code_repository"
    description = "Build a local metadata-only index of a configured source repository without executing code."

    async def run(self, root: str | None = None) -> dict[str, Any]:
        try:
            index = await repository_indexer.build(root)
        except CodePolicyError as exc:
            raise ToolError(str(exc)) from exc
        return {
            "root": str(index.root),
            "file_count": len(index.files),
            "created_at": index.created_at,
            "status": "indexed",
        }


class AnalyzeCodeRepositoryTool(Tool):
    name = "analyze_code_repository"
    description = "Analyze project structure, languages, symbols, entrypoints, and read-only Git status."

    async def run(self, root: str | None = None) -> dict[str, Any]:
        try:
            return await repository_indexer.analyze(root)
        except CodePolicyError as exc:
            raise ToolError(str(exc)) from exc


class SearchCodeRepositoryTool(Tool):
    name = "search_code_repository"
    description = "Search a configured source repository by path, symbol, or bounded source text."

    async def run(self, query: str, mode: str = "text", root: str | None = None) -> dict[str, Any]:
        try:
            return await repository_indexer.search(query=query, mode=mode, raw_root=root)
        except CodePolicyError as exc:
            raise ToolError(str(exc)) from exc


class CodeRepositoryStatusTool(Tool):
    name = "code_repository_status"
    description = "Read the local code-index status without reading source content."

    async def run(self) -> dict[str, Any]:
        return {"repositories": repository_indexer.status()}
