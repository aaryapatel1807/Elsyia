# Phase 10 Attachment Processing Contract

**Milestone:** Local attachment summaries and approval-gated memory proposals  
**Status:** In progress

## Scope

After a file is accepted by the normalized input layer, Elsyia may enqueue a bounded background processing job. The first processor supports UTF-8 text-like files and code documents only. Images, audio, video, and PDF attachments remain stored safely but are reported as unsupported until dedicated local extractors are added.

Processing is asynchronous and never blocks the ingest response or the voice/chat response path. The job stores status and a bounded summary locally so the desktop UI can display progress.

## Local-model policy

The configured model is used only when `INPUT_PROCESSING_ENABLED=true`. By default, processing is restricted to the local Ollama provider. If the configured provider is OpenRouter or Gemini, processing is blocked unless `INPUT_PROCESSING_ALLOW_CLOUD=true` is explicitly set by the user in `.env`. No attachment is silently uploaded to a cloud provider.

> A summary is an interpretation of untrusted file data. The processor must ignore instructions embedded in the file and treat the file exclusively as content to summarize.

## Processing flow

| Stage | Behavior |
|---|---|
| Ingest | Copy and validate the original file into the private attachment store |
| Queue | Create one bounded local processing job for the attachment |
| Extract | Read only supported text-like extensions up to the configured character limit |
| Summarize | Ask the configured model for a concise summary with a strict output bound |
| Memory proposal | Optionally save one `approved=false` pending memory sourced from the attachment summary |
| Review | User reviews the proposal in the existing Memory panel and explicitly approves or deletes it |
| Retention | Attachment expiry removes the copied file; its job and summary remain metadata-only unless cleanup policy removes them later |

## Memory safety

Attachment summaries are never inserted into approved memory automatically. A proposal is stored with `source="attachment"`, `approved=false`, and a bounded `category="document"`. The existing memory approval endpoint and panel remain the only path to durable retrieval.

Secret-like summaries containing terms such as password, token, API key, credential, private key, or secret do not create memory proposals. The summary itself remains local and is redacted from audit logs. Users may delete pending proposals through the existing memory controls.

## Limits

| Setting | Default |
|---|---:|
| Maximum extracted text | 12,000 characters |
| Maximum summary output | 2,000 characters |
| Maximum memory proposals per job | 1 |
| Worker concurrency | 1 job at a time |
| Worker poll interval | 2 seconds |
| Cloud processing | Disabled unless explicitly enabled |

## API additions

```http
POST /api/v1/input/attachments/{token}/process
GET  /api/v1/input/processing/{job_id}
```

The attachment list exposes the latest processing status, job ID, summary, and pending proposal IDs. Raw extracted content and absolute source paths are never returned by the API.

## Audit policy

Audit records include the job ID, attachment token, provider class, status, character count, and proposal count. They never include raw file content, complete display paths, prompt text, summary text, or API credentials.
