"""Safe, bounded local file tools for Phase 3."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, Iterable

from app.core import get_settings
from app.services.llm.factory import create_llm_provider
from app.services.tools.base import Tool, ToolError

_TEXT_EXTENSIONS = {
    ".c",
    ".cfg",
    ".conf",
    ".cpp",
    ".css",
    ".csv",
    ".h",
    ".hpp",
    ".html",
    ".ini",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".log",
    ".md",
    ".py",
    ".rs",
    ".sql",
    ".tex",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}


def _configured_roots() -> list[Path]:
    settings = get_settings()
    configured = [part.strip() for part in settings.TOOLS_FILE_ROOTS.split(",") if part.strip()]
    if not configured:
        home = Path.home()
        configured = [str(home / name) for name in ("Desktop", "Documents", "Downloads")]
    roots: list[Path] = []
    for raw_root in configured:
        root = Path(os.path.expandvars(os.path.expanduser(raw_root))).resolve()
        if root.exists() and root.is_dir() and root not in roots:
            roots.append(root)
    return roots


def _excluded_dirs() -> set[str]:
    return {
        part.strip()
        for part in get_settings().TOOLS_EXCLUDED_DIRS.split(",")
        if part.strip()
    }


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _safe_path(raw_path: str) -> tuple[Path, Path]:
    candidate = Path(os.path.expandvars(os.path.expanduser(raw_path))).resolve()
    for root in _configured_roots():
        if _is_within(candidate, root) and candidate.is_file():
            return candidate, root
    raise ToolError("The requested file is outside the configured local tool roots or does not exist.")


def _iter_files(root: Path) -> Iterable[Path]:
    excluded = _excluded_dirs()
    try:
        for current_root, dirs, files in os.walk(root, topdown=True, followlinks=False):
            dirs[:] = sorted(directory for directory in dirs if directory not in excluded)
            for filename in sorted(files):
                path = Path(current_root) / filename
                if path.is_file() and not path.is_symlink():
                    yield path
    except OSError as exc:
        raise ToolError(f"Could not read the configured folder: {exc}") from exc


def _read_text(path: Path) -> str:
    settings = get_settings()
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ToolError("Could not inspect that file.") from exc
    if size > settings.TOOLS_MAX_FILE_BYTES:
        raise ToolError(
            f"The file is too large to inspect safely ({size} bytes; limit {settings.TOOLS_MAX_FILE_BYTES})."
        )
    if path.suffix.lower() not in _TEXT_EXTENSIONS:
        raise ToolError("Only supported text-like document formats can be inspected.")
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise ToolError("Could not read that document.") from exc


class SearchLocalFilesTool(Tool):
    """Search configured local roots by filename and optionally text content."""

    name = "search_local_files"
    description = (
        "Search the user's configured local Desktop, Documents, or Downloads roots by filename "
        "or text content. Read-only and bounded; never searches outside allowed roots."
    )

    async def run(
        self,
        query: str,
        mode: str = "name",
        root: str | None = None,
        max_results: int | None = None,
    ) -> dict[str, Any]:
        normalized_query = " ".join(query.strip().split()).lower()
        if len(normalized_query) < 2:
            raise ToolError("Search query must contain at least two characters.")
        if mode not in {"name", "content"}:
            raise ToolError("Search mode must be 'name' or 'content'.")
        settings = get_settings()
        limit = min(max_results or settings.TOOLS_MAX_RESULTS, settings.TOOLS_MAX_RESULTS)
        roots = _configured_roots()
        if root:
            requested_root = Path(os.path.expandvars(os.path.expanduser(root))).resolve()
            allowed = any(_is_within(requested_root, candidate) for candidate in roots)
            roots = [requested_root] if allowed and requested_root.is_dir() else []
        if not roots:
            raise ToolError("No configured local search roots are available.")

        matches: list[dict[str, Any]] = []
        for search_root in roots:
            for path in _iter_files(search_root):
                if mode == "name":
                    matched = normalized_query in path.name.lower()
                    snippet = None
                else:
                    if path.suffix.lower() not in _TEXT_EXTENSIONS:
                        continue
                    try:
                        content = _read_text(path)
                    except ToolError:
                        continue
                    matched = normalized_query in content.lower()
                    snippet = None
                    if matched:
                        index = content.lower().find(normalized_query)
                        snippet = " ".join(content[max(0, index - 80) : index + len(normalized_query) + 160].split())
                if matched:
                    record: dict[str, Any] = {
                        "path": str(path),
                        "name": path.name,
                        "size_bytes": path.stat().st_size,
                    }
                    if snippet:
                        record["snippet"] = snippet[:300]
                    matches.append(record)
                    if len(matches) >= limit:
                        return {"query": query, "mode": mode, "matches": matches, "truncated": True}
        return {"query": query, "mode": mode, "matches": matches, "truncated": False}


class SummarizeLocalDocumentTool(Tool):
    """Read one allowed text document and summarize it through the configured LLM."""

    name = "summarize_local_document"
    description = (
        "Summarize a local text document inside the configured safe roots using the configured "
        "assistant model. The document is bounded and is not uploaded by this tool."
    )

    async def run(self, path: str, focus: str | None = None) -> dict[str, Any]:
        document_path, _ = _safe_path(path)
        content = await asyncio.to_thread(_read_text, document_path)
        settings = get_settings()
        truncated = len(content) > settings.TOOLS_MAX_SUMMARY_CHARS
        bounded_content = content[: settings.TOOLS_MAX_SUMMARY_CHARS]
        focus_text = focus.strip() if focus else "the main points and actionable details"
        prompt = (
            "Summarize the following local document concisely. Focus on "
            f"{focus_text}. Do not invent facts, and state when the excerpt is truncated.\n\n"
            f"Document: {document_path.name}\n"
            f"Truncated: {truncated}\n\n"
            f"{bounded_content}"
        )
        try:
            provider = create_llm_provider(settings.DEFAULT_LLM_PROVIDER)
            chunks: list[str] = []
            async for token in provider.generate(
                [
                    {
                        "role": "system",
                        "content": "You are a concise local document summarizer. Return only the summary.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=384,
            ):
                chunks.append(token)
            summary = "".join(chunks).strip()
        except Exception as exc:
            raise ToolError("The configured local model could not summarize this document.") from exc
        if not summary:
            raise ToolError("The summarizer returned an empty result.")
        return {
            "path": str(document_path),
            "summary": summary,
            "characters_read": len(bounded_content),
            "truncated": truncated,
        }
