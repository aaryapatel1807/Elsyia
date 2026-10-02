# Phase 10 Progress Report: Input Abstraction and Drag-and-Drop Files

**Project:** Elsyia  
**Phase:** 10 — Multi-Modal Input  
**Milestone:** Normalized local input events and secure drag-and-drop file ingestion  
**Status:** In progress  
**Author:** Manus AI

## Summary

Phase 10 development has started with the local-first input abstraction layer and desktop file ingestion foundation. Dropped files are validated by the backend, copied into a private Elsyia attachment directory, represented by normalized metadata, and retained only for a bounded period. The original user file is never modified or deleted.

This milestone intentionally does not send attachment content to an LLM, cloud provider, browser, tool, or long-term memory. It establishes a safe attachment boundary that later camera, clipboard, screenshot, handwriting, and mobile inputs can reuse.

## Implemented components

| Area | Implementation | Status |
|---|---|---|
| Input model | `InputEvent` with source, kind, conversation, privacy, retention, timestamps, and attachment metadata | Complete |
| Attachment persistence | SQLite metadata store using explicit commits and local file copies | Complete |
| Safe-root policy | Resolved-path containment, traversal protection, regular-file check, and symlink rejection | Complete |
| File policy | Extension allowlist, file-count limit, per-file limit, total-drop limit, and total-storage limit | Complete |
| Privacy | Local-only copies, tokenized storage names, digest prefixes, and redacted audit arguments | Complete |
| Retention | Expiry timestamps, deletion endpoint, cleanup endpoint, startup cleanup, and periodic cleanup worker | Complete |
| REST API | Ingest, list, delete, cleanup, and status routes under `/api/v1/input` | Complete |
| Desktop UI | React/Electron drop zone with choose-file fallback, status feedback, attachment list, and deletion | Complete |
| Chat processing | Automatic LLM or memory injection from attachments | Deferred by design |

## API contract

```http
POST /api/v1/input/ingest
GET  /api/v1/input/attachments
DELETE /api/v1/input/attachments/{token}
POST /api/v1/input/cleanup
GET  /api/v1/input/status
```

The ingest request contains local desktop paths and an optional conversation ID. The backend returns attachment tokens and bounded metadata such as display name, extension, byte size, MIME type, digest prefix, privacy classification, and expiration time. Raw file contents are never returned by these endpoints.

## Configuration

Phase 10 settings are documented in `.env.example` and include `INPUT_ENABLED`, `INPUT_SAFE_ROOTS`, `INPUT_ATTACHMENT_DIR`, per-drop and per-file limits, attachment retention, and the allowed-extension list. `INPUT_SAFE_ROOTS` is intentionally explicit; an empty value rejects ingestion instead of silently granting broad filesystem access.

## Safety decisions

The implementation follows the project’s local-first safety policy. It copies rather than moves source files, rejects unsupported extensions and executables, rejects symbolic links, refuses paths outside configured roots, bounds file counts and bytes, and records only redacted audit metadata. Attachment copies expire automatically and can be deleted by token. Attachments are classified as private or sensitive and are not automatically saved to memory.

The cleanup worker runs in the background and uses a bounded periodic interval so request handling is not blocked. The first version returns metadata only; future processors must require explicit selection before extracting content or invoking a model.

## Verification

The regression suite is located at `scripts/test-phase10-input.py` and covers safe-root rejection, extension and size rejection, symlink rejection where supported, multiple-file ingestion, total-drop limits, persistence after reopening the SQLite store, deletion, expiry cleanup, and API integration. Compilation and frontend production-build verification should be run from the attached Windows checkout after the local development process is responsive.

## Remaining Phase 10 milestones

Camera capture, explicit clipboard capture, screenshot annotation, handwriting OCR, multi-microphone selection, touch and controller input, and mobile synchronization remain future milestones. They will reuse the normalized event and attachment contracts and must add visible consent indicators, device permission controls, bounded payloads, and immediate stop/delete controls before implementation.

## Files added or updated

- `backend/app/services/input/manager.py`
- `backend/app/services/input/__init__.py`
- `backend/app/models/input.py`
- `backend/app/api/v1/input.py`
- `backend/app/api/v1/router.py`
- `backend/app/main.py`
- `backend/app/core/config.py`
- `frontend/src/components/DropZone.tsx`
- `frontend/src/App.tsx`
- `.env.example`
- `docs/MULTIMODAL-INPUT.md`
- `docs/ROADMAP.md`
- `scripts/test-phase10-input.py`

## Next milestone: attachment processing

The next Phase 10 milestone is now implemented for text and code attachments. Accepted files can automatically enter a persistent local processing queue. A single background worker reads only bounded UTF-8 text-like content, asks the configured model for a concise summary, stores bounded job state in the local input database, and exposes progress through the attachment API and desktop drop zone.

Processing is restricted to the local Ollama provider by default. OpenRouter or Gemini processing is rejected unless `INPUT_PROCESSING_ALLOW_CLOUD=true` is explicitly configured. This prevents a cloud provider from receiving attachment content merely because it is selected as the general chat provider.

Summaries can create at most one **pending memory proposal** per job. The proposal uses `source="attachment"` and `approved=false`, so it cannot affect future memory retrieval until the user approves it through the existing Memory panel. Secret-like summaries containing password, token, API key, credential, private key, or secret terminology do not create proposals.

### Processing routes

```http
POST /api/v1/input/attachments/{token}/process
GET  /api/v1/input/processing/{job_id}
```

The attachment list now includes the latest job status, bounded summary, provider name, extraction count, truncation flag, and pending proposal IDs. The UI polls only while a job is queued or running and displays completed summaries and a reminder to review pending memory proposals.

### Verification update

Backend compilation passed. The focused processing suite passed all five tests, including local-model summary handling, text bounds and truncation, secret-aware memory suppression, unsupported-file failure behavior, and cloud-provider blocking. The original Phase 10 input suite passed with one environment-dependent symlink test skipped where symlink creation was unavailable. The frontend production build passed; Vite emitted only the existing large-chunk advisory.

Image, audio, video, PDF extraction, OCR, camera, clipboard, screenshot, and mobile processing remain future milestones. They must add dedicated local extractors and the same explicit consent, bounded-resource, deletion, and cloud-egress controls before activation.
