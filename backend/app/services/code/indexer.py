"""Local-first repository indexing and static code search for Phase 7."""

from __future__ import annotations

import ast
import asyncio
import hashlib
import json
import os
import re
import subprocess
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from app.core import get_settings


class CodePolicyError(Exception):
    """Raised when a repository request violates the local code policy."""


_LANGUAGE_BY_EXTENSION = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".java": "Java",
    ".c": "C",
    ".h": "C",
    ".cpp": "C++",
    ".hpp": "C++",
    ".go": "Go",
    ".rs": "Rust",
    ".json": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".md": "Markdown",
    ".html": "HTML",
    ".css": "CSS",
    ".sql": "SQL",
    ".sh": "Shell",
}


def _split_setting(value: str) -> set[str]:
    return {part.strip() for part in value.split(",") if part.strip()}


def _roots() -> list[Path]:
    settings = get_settings()
    if not settings.CODE_ENABLED:
        return []
    roots: list[Path] = []
    for raw in settings.CODE_REPOSITORY_ROOTS.split(","):
        if not raw.strip():
            continue
        path = Path(os.path.expandvars(os.path.expanduser(raw.strip()))).resolve()
        if path.exists() and path.is_dir() and not path.is_symlink() and path not in roots:
            roots.append(path)
    return roots


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def resolve_repository(raw_root: str | None = None) -> Path:
    roots = _roots()
    if not roots:
        raise CodePolicyError("Code analysis is disabled until CODE_REPOSITORY_ROOTS is configured.")
    if raw_root:
        requested = Path(os.path.expandvars(os.path.expanduser(raw_root))).resolve()
        for root in roots:
            if requested == root or _inside(requested, root):
                if requested.is_dir() and not requested.is_symlink():
                    return requested
        raise CodePolicyError("Requested repository is outside the configured code roots.")
    if len(roots) == 1:
        return roots[0]
    raise CodePolicyError("Specify one repository root because multiple code roots are configured.")


def _excluded() -> set[str]:
    return _split_setting(get_settings().CODE_EXCLUDED_DIRS)


def _extensions() -> set[str]:
    return {extension.lower() for extension in _split_setting(get_settings().CODE_SUPPORTED_EXTENSIONS)}


def _iter_source_files(root: Path) -> Iterable[Path]:
    excluded = _excluded()
    extensions = _extensions()
    max_files = get_settings().CODE_MAX_FILES
    seen = 0
    for current_root, dirs, files in os.walk(root, topdown=True, followlinks=False):
        dirs[:] = sorted(
            directory
            for directory in dirs
            if directory not in excluded and not (Path(current_root) / directory).is_symlink()
        )
        for filename in sorted(files):
            path = Path(current_root) / filename
            if path.is_symlink() or path.suffix.lower() not in extensions:
                continue
            yield path
            seen += 1
            if seen >= max_files:
                return


def _read_source(path: Path) -> tuple[str, int]:
    max_bytes = get_settings().CODE_MAX_FILE_BYTES
    try:
        size = path.stat().st_size
    except OSError:
        return "", 0
    if size > max_bytes:
        return "", size
    try:
        return path.read_text(encoding="utf-8", errors="replace"), size
    except OSError:
        return "", size


def _python_symbols(source: str) -> list[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    symbols: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.append(node.name)
    return sorted(set(symbols))[:200]


def _generic_symbols(source: str, language: str) -> list[str]:
    patterns = {
        "JavaScript": r"\b(?:function|class|const|let|var)\s+([A-Za-z_$][\w$]*)",
        "TypeScript": r"\b(?:function|class|interface|type|const|let|var)\s+([A-Za-z_$][\w$]*)",
        "Java": r"\b(?:class|interface|enum|void|public|private|protected)\s+([A-Za-z_$][\w$]*)",
        "Go": r"\b(?:func|type|var|const)\s+([A-Za-z_][\w]*)",
        "Rust": r"\b(?:fn|struct|enum|trait|mod|const)\s+([A-Za-z_][\w]*)",
        "C": r"\b(?:struct|enum|typedef|class)\s+([A-Za-z_][\w]*)",
        "C++": r"\b(?:struct|enum|typedef|class|namespace)\s+([A-Za-z_][\w]*)",
    }
    pattern = patterns.get(language)
    if not pattern:
        return []
    return sorted(set(re.findall(pattern, source)))[:200]


def _file_record(root: Path, path: Path) -> dict[str, Any]:
    source, size = _read_source(path)
    language = _LANGUAGE_BY_EXTENSION.get(path.suffix.lower(), "Unknown")
    relative = path.relative_to(root).as_posix()
    digest = hashlib.sha256(source.encode("utf-8", errors="replace")).hexdigest() if source else ""
    symbols = _python_symbols(source) if language == "Python" else _generic_symbols(source, language)
    return {
        "path": relative,
        "language": language,
        "size_bytes": size,
        "line_count": source.count("\n") + (1 if source else 0),
        "modified_at": path.stat().st_mtime,
        "sha256": digest,
        "symbols": symbols,
        "readable": bool(source) or size == 0,
    }


@dataclass
class RepositoryIndex:
    root: Path
    files: list[dict[str, Any]]
    created_at: float

    def as_dict(self) -> dict[str, Any]:
        languages = Counter(record["language"] for record in self.files)
        return {
            "root": str(self.root),
            "created_at": self.created_at,
            "file_count": len(self.files),
            "languages": dict(sorted(languages.items())),
            "files": self.files,
        }


class RepositoryIndexer:
    def __init__(self) -> None:
        self._indexes: dict[str, RepositoryIndex] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock_for(self, root: Path) -> asyncio.Lock:
        key = str(root)
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    async def build(self, raw_root: str | None = None) -> RepositoryIndex:
        root = resolve_repository(raw_root)
        async with self._lock_for(root):
            files = await asyncio.to_thread(lambda: [_file_record(root, path) for path in _iter_source_files(root)])
            index = RepositoryIndex(root=root, files=files, created_at=time.time())
            self._indexes[str(root)] = index
            await asyncio.to_thread(self._write_cache, index)
            return index

    def _write_cache(self, index: RepositoryIndex) -> None:
        raw_cache = Path(get_settings().CODE_INDEX_CACHE_PATH)
        cache_path = (raw_cache if raw_cache.is_absolute() else resolve_repository(str(index.root)) / raw_cache).resolve()
        if not _inside(cache_path, index.root):
            cache_path = index.root / ".elysia" / "code_index.json"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(index.as_dict(), indent=2), encoding="utf-8")

    async def get_or_build(self, raw_root: str | None = None) -> RepositoryIndex:
        root = resolve_repository(raw_root)
        existing = self._indexes.get(str(root))
        if existing is not None:
            return existing
        return await self.build(str(root))

    async def search(self, query: str, mode: str = "text", raw_root: str | None = None) -> dict[str, Any]:
        normalized = " ".join(query.strip().split()).lower()
        if len(normalized) < 2:
            raise CodePolicyError("Code search query must contain at least two characters.")
        if mode not in {"text", "path", "symbol"}:
            raise CodePolicyError("Code search mode must be text, path, or symbol.")
        index = await self.get_or_build(raw_root)
        limit = get_settings().CODE_MAX_RESULTS
        results: list[dict[str, Any]] = []
        for record in index.files:
            haystack = record["path"].lower() if mode == "path" else " ".join(record["symbols"]).lower() if mode == "symbol" else ""
            matched = normalized in haystack
            snippet = None
            if mode == "text":
                path = index.root / record["path"]
                source, _size = _read_source(path)
                position = source.lower().find(normalized)
                matched = position >= 0
                if matched:
                    limit_chars = get_settings().CODE_MAX_SNIPPET_CHARS
                    start = max(0, position - limit_chars // 3)
                    snippet = " ".join(source[start : start + limit_chars].split())
            if matched:
                result = {"path": record["path"], "language": record["language"], "symbols": record["symbols"][:20]}
                if snippet:
                    result["snippet"] = snippet
                results.append(result)
                if len(results) >= limit:
                    return {"root": str(index.root), "query": query, "mode": mode, "matches": results, "truncated": True}
        return {"root": str(index.root), "query": query, "mode": mode, "matches": results, "truncated": False}

    async def analyze(self, raw_root: str | None = None) -> dict[str, Any]:
        index = await self.get_or_build(raw_root)
        languages = Counter(record["language"] for record in index.files)
        total_lines = sum(record["line_count"] for record in index.files)
        symbols = sum(len(record["symbols"]) for record in index.files)
        entrypoints = [
            record["path"]
            for record in index.files
            if Path(record["path"]).name.lower()
            in {"pyproject.toml", "package.json", "go.mod", "cargo.toml", "pom.xml", "makefile", "dockerfile"}
        ]
        git_branch, git_changed = await asyncio.to_thread(self._git_status, index.root)
        return {
            "root": str(index.root),
            "file_count": len(index.files),
            "total_lines": total_lines,
            "symbol_count": symbols,
            "languages": dict(sorted(languages.items())),
            "entrypoints": entrypoints[:50],
            "git_branch": git_branch,
            "git_has_changes": git_changed,
            "index_created_at": index.created_at,
        }

    @staticmethod
    def _git_status(root: Path) -> tuple[str | None, bool]:
        try:
            completed = subprocess.run(
                ["git", "-C", str(root), "status", "--porcelain", "-b"],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
                shell=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None, False
        lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
        branch = lines[0].removeprefix("## ") if lines and lines[0].startswith("## ") else None
        return branch, len(lines) > 1

    def status(self) -> list[dict[str, Any]]:
        return [
            {"root": str(index.root), "file_count": len(index.files), "created_at": index.created_at}
            for index in self._indexes.values()
        ]


repository_indexer = RepositoryIndexer()
