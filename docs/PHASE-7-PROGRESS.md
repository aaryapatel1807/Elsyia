# Elsyia Phase 7 Code Assistant Foundation

**Verification date:** August 20, 2026  
**Milestone:** Local repository indexing, static project analysis, and bounded code search  
**Status:** Foundation implemented and verified

## Completed capabilities

| Capability | Result |
|---|---|
| Trusted repository roots | Explicit `CODE_REPOSITORY_ROOTS` policy; empty means disabled |
| Safe path handling | Outside roots and symlinked paths rejected |
| Bounded indexing | File count, file-size, extension, and excluded-directory limits |
| Metadata-only index | Relative path, language, bytes, lines, timestamp, digest, and symbols; no full source persisted |
| Python analysis | Standard-library AST extraction of classes and functions |
| Multi-language analysis | Conservative symbol extraction for JavaScript/TypeScript, Java, C/C++, Go, and Rust |
| Keyword search | Path, symbol, and bounded source-text modes |
| Project analysis | Language inventory, file count, line count, symbol count, entrypoints, and read-only Git status |
| API | Index, analyze, search, and status endpoints under `/api/v1/code` |
| Tool registry | Shared structured results, rate/timeout behavior, and redacted audit integration |
| Voice/chat routing | Added repository analysis, indexing, and code-search command patterns |
| Code-change safety | No generation, patching, refactoring, test execution, or shell execution enabled |

## Architecture

```text
Voice/text request
    -> deterministic code intent router
    -> code API or shared tool registry
    -> repository policy
    -> local metadata-only index
    -> path/symbol/text search or static project analysis
    -> bounded structured result + redacted local audit event
```

The indexer never imports or executes repository modules. Python AST parsing is performed on source text, while other languages use conservative regular-expression symbol extraction. Git status is inspected through a read-only `git status --porcelain -b` command with a short timeout and no shell interpolation.

## Privacy policy

Repository analysis remains local. The index stores metadata and SHA-256 digests, not full source. Search snippets are generated only for the current request and are bounded by `CODE_MAX_SNIPPET_CHARS`. Dependency, build, cache, and version-control directories are excluded by default.

Source comments and documentation are untrusted data. They cannot grant permissions, change safety policy, authorize a code edit, or trigger execution. Cloud providers are not used by the foundation tools.

## API

```http
POST /api/v1/code/index
{"root":"C:/path/to/project"}

POST /api/v1/code/analyze
{"root":"C:/path/to/project"}

POST /api/v1/code/search
{"root":"C:/path/to/project","query":"Widget","mode":"symbol"}

GET /api/v1/code/status
```

The same capabilities are available as `index_code_repository`, `analyze_code_repository`, `search_code_repository`, and `code_repository_status` through the shared tool catalog.

## Configuration

```env
CODE_ENABLED=true
CODE_REPOSITORY_ROOTS=
CODE_MAX_FILES=5000
CODE_MAX_FILE_BYTES=1000000
CODE_MAX_RESULTS=50
CODE_MAX_SNIPPET_CHARS=600
CODE_EXCLUDED_DIRS=.git,.hg,.svn,node_modules,.venv,venv,__pycache__,dist,build,coverage
CODE_INDEX_CACHE_PATH=data/code_index.json
```

Keep the repository-root setting empty until the user explicitly chooses local projects for analysis.

## Verification

| Check | Result |
|---|---|
| Backend compilation | Passed |
| Repository policy escape test | Passed |
| Excluded dependency directory test | Passed |
| Binary-file exclusion test | Passed |
| Python AST symbol extraction | Passed |
| Path/symbol/text search | Passed |
| Metadata-only cache assertion | Passed |
| FastAPI code API integration | Passed |
| Deterministic code command routing | Passed |
| Browser foundation suite | Passed |
| Phase 5 desktop suite | Passed |
| Phase 4 plugin suite | Passed |
| Existing tool suite | Passed |
| Provider adapter suite | Passed |
| Formal pytest suite | Passed |
| Frontend TypeScript and production build | Passed |

The existing non-blocking Vite warning about the JavaScript bundle exceeding 500 kB remains.

## Future Phase 7 milestones

The next milestone should add semantic code search using local embeddings, followed by read-only code explanations and review. Code generation, refactoring, patch application, test generation, and test execution require a separate preview, backup, recovery, and confirmation workflow before they are enabled.
