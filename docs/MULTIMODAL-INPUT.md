# Elsyia Phase 10 Input Abstraction and File Ingestion

**Milestone:** Normalized input events and secure drag-and-drop file ingestion  
**Status:** Architecture defined; implementation follows this contract

## Input abstraction

Every non-voice input is normalized into an `InputEvent` with a generated event ID, source, kind, conversation ID when available, timestamp, attachment metadata, privacy classification, and retention policy.

| Field | Examples | Policy |
|---|---|---|
| `source` | `desktop_drop`, `clipboard`, `camera`, `mobile` | Enumerated source; unknown sources rejected |
| `kind` | `file`, `image`, `text`, `audio`, `video` | Determines validation and downstream handling |
| `conversation_id` | Existing chat session | Optional, locally stored |
| `attachment` | Name, MIME, size, digest, local token | Metadata only in event log |
| `privacy` | `sensitive`, `private`, `normal` | Defaults to sensitive for clipboard and unknown files |
| `retention` | `session`, `until_deleted`, `expires` | User-controlled; default is session |

The event record never stores raw file bytes or full sensitive text. It references a local attachment token that can be deleted independently.

## Drag-and-drop file policy

The desktop accepts dropped files only through the visible Electron/React drop zone. The backend never trusts a client-provided path by itself. It validates the resolved path against `INPUT_SAFE_ROOTS`, rejects symlinks, directories, reparse points, traversal, and paths outside configured roots, then copies the file into an Elsyia-managed local attachment directory.

Files are copied rather than moved. The original user file is never modified or deleted by ingestion. The copied attachment receives a random token filename, original display name as metadata, byte size, extension, MIME guess, SHA-256 digest, creation time, and expiry state.

## Limits

| Limit | Default |
|---|---:|
| Maximum files per drop | 10 |
| Maximum bytes per file | 10 MB |
| Maximum total drop bytes | 50 MB |
| Maximum stored attachments | 1000 |
| Session retention | 24 hours |
| Allowed file classes | Text, code, JSON/YAML, PDF, common images, audio, and video metadata |
| Executables | Rejected by default |

Archives, installers, scripts intended for execution, credential files, and OS database files are rejected or marked sensitive. Ingestion does not execute, preview through an external application, import, or parse untrusted code.

## Privacy and retention

Dropped files remain local. The audit log records event ID, status, source, size, digest prefix, and redacted display name; it does not record raw contents or absolute client paths. Attachments are not placed into long-term memory automatically. A user must explicitly save a derived fact or summary.

Session attachments expire automatically. The UI exposes deletion for every attachment and a clear-all action. Cleanup runs at backend startup and periodically while the process is active. Deletion removes the Elsyia copy only; it does not touch the original file.

## Processing contract

The first milestone returns an attachment preview and normalized event. It does not automatically send content to an LLM, browser, cloud provider, or memory store. Future chat integration must pass only the selected attachment token and bounded extracted content to the explicitly chosen local processor.

## Processing extension

Text and code attachments may be queued for background processing after ingestion. The processor reads only a bounded local excerpt, uses Ollama by default, stores a bounded summary in the local processing-job table, and may create one pending attachment-derived memory proposal. The existing memory approval workflow remains mandatory; no attachment summary becomes retrievable memory automatically. See `docs/INPUT-PROCESSING.md` for the detailed contract.

## Safety acceptance criteria

The implementation is ready when it can accept multiple dropped local files, reject unsafe paths and file types, enforce per-file and total-size limits, copy files into a private local directory, return stable attachment tokens and metadata, delete attachments safely, expire old files, and pass tests proving original files remain unchanged and raw content is absent from audit events.
