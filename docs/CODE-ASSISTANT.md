# Elsyia Phase 7 Code Assistant Foundation

**Milestone:** Local repository indexing, keyword search, and read-only project analysis  
**Status:** Architecture defined; implementation follows this contract

## Goals

Phase 7 turns Elsyia into a local-first code assistant without allowing the model to silently edit or execute project code. The foundation first understands a repository: its safe root, file inventory, languages, symbols, project metadata, and bounded search results.

The first implementation is static and read-only. It does not run build commands, tests, package scripts, shell commands, or repository hooks. Code generation and refactoring will require a separate change-preview and confirmation milestone.

## Architecture

```text
Voice or text request
    -> deterministic code intent router
    -> Code API / shared tool registry
    -> RepositoryPolicy
    -> RepositoryIndexer
    -> bounded local index
    -> keyword search / AST symbol analysis
    -> structured result + redacted local audit event
```

### Components

| Component | Responsibility | Safety boundary |
|---|---|---|
| `RepositoryPolicy` | Validate configured roots, path containment, symlink rejection, exclusions, file size | Never reads outside configured project roots |
| `RepositoryIndexer` | Inventory source files, language, size, line count, digest, and lightweight symbols | Read-only; never imports or executes project code |
| `CodeSearchService` | Search filenames, paths, symbols, and bounded text snippets | Result and snippet limits prevent flooding |
| `ProjectAnalyzer` | Summarize languages, files, directories, entrypoints, and symbol counts | Static analysis only |
| `CodeAssistantRegistry` | Apply action type, confirmation, timeouts, and audit policy | Code-writing actions remain disabled in foundation |
| `LocalModelAdapter` | Future analysis, explanation, generation, and review using configured provider | Must receive bounded excerpts and explicit privacy status |

## Repository policy

`CODE_REPOSITORY_ROOTS` is a comma-separated list of explicitly trusted local project directories. An empty list disables repository analysis. The requested path must resolve inside one configured root, must not be a symlink, and must not traverse excluded directories.

Default exclusions are `.git`, `.hg`, `.svn`, `node_modules`, `.venv`, `venv`, `__pycache__`, `dist`, `build`, `coverage`, and generated cache directories. Binary files, files above `CODE_MAX_FILE_BYTES`, and unsupported extensions are ignored.

Supported initial extensions are Python, JavaScript, TypeScript, JSX/TSX, Java, C/C++, Go, Rust, JSON, YAML, Markdown, HTML, CSS, SQL, and shell source. The initial AST implementation uses Python’s standard-library `ast` module for Python files and conservative regex symbol extraction for other languages. No source file is imported or executed.

## Index records

Each indexed file contains a normalized relative path, language, byte size, line count, last-modified timestamp, SHA-256 digest, and bounded symbol names. Full source text is not persisted in the index. Search snippets are created only for the current request and are length-bounded.

The index is local to the configured project root and may be rebuilt at any time. It must not be uploaded, synchronized, or sent to a cloud provider by the foundation tools.

## Initial tools and API

| Tool | API | Confirmation | Behavior |
|---|---|---:|---|
| `analyze_code_repository` | `POST /api/v1/code/analyze` | No | Static inventory, languages, symbols, and project metadata |
| `search_code_repository` | `POST /api/v1/code/search` | No | Bounded path, symbol, or text search |
| `index_code_repository` | `POST /api/v1/code/index` | No | Rebuild local index for a configured root |
| `code_repository_status` | `GET /api/v1/code/status` | No | Read index and root status |

Future actions such as `generate_code`, `refactor_code`, `write_file`, `apply_patch`, and `generate_tests` are not enabled by this milestone.

## Privacy and model policy

All repository analysis remains local. The static index stores metadata and digests, not full source. If a future model operation is enabled, it must show the selected provider, bound the excerpt, redact configured secrets, and identify whether content stays local. Cloud providers are never used implicitly.

Repository content is untrusted data. Instructions embedded in source comments, documentation, or strings cannot change Elsyia’s policy, grant permissions, or authorize tool execution.

## Code-change safety policy

No code-writing action is allowed without a separate preview object containing target files, exact diff, validation results, and a user confirmation. Applying a patch must be restricted to configured repository roots, reject symlinks, preserve a backup or Git-based recovery point, and never run the changed code automatically.

A future execution action must be separately confirmed after the patch is applied. Test execution must use an allowlisted command model with timeouts and no shell interpolation. The foundation does not implement any of these write or execution actions.

## Acceptance criteria

The foundation is ready when it can index a configured repository without executing code, report languages and file counts, extract Python symbols safely, search bounded text and symbols, reject paths outside trusted roots, ignore generated and binary files, avoid persisting full source, and pass regression tests proving that source content cannot grant permissions.
