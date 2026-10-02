# Elysia Persistent Memory

Phase 2 provides a local, user-controlled memory store backed by SQLite. Explicitly saved memories are approved immediately. Background-extracted preferences are stored as **pending** and are not injected into chat until the user approves them in the Memory panel.

The database defaults to `data/elysia_memory.db`. Each memory stores timestamps, scope, category, provenance, approval state, an embedding version, and an optional encrypted content value. The active semantic backend is the local Ollama `nomic-embed-text` transformer, which produces 768-dimensional vectors. Retrieval combines neural similarity with lexical overlap and falls back to a deterministic local vector embedder when the neural model is unavailable or exceeds its latency budget.

## API

Save an explicit memory:

```http
POST /api/v1/memory/
Content-Type: application/json

{"content":"Aarya prefers concise spoken answers.","category":"preference"}
```

List approved memories:

```http
GET /api/v1/memory/?scope=default
```

List approved and pending memories for review:

```http
GET /api/v1/memory/?scope=default&include_pending=true
```

Approve a pending memory:

```http
POST /api/v1/memory/{id}/approve?scope=default
```

Delete one memory or clear a scope:

```http
DELETE /api/v1/memory/{id}?scope=default
DELETE /api/v1/memory/?scope=default
```

Rebuild vectors after changing the embedding model or version:

```http
POST /api/v1/memory/reindex?scope=default
```

Export decrypted user-visible memories for backup:

```http
GET /api/v1/memory/export?scope=default
```

Read privacy-safe counts and index state:

```http
GET /api/v1/memory/stats?scope=default
```

## Privacy controls

Memory content remains local by default. Set `MEMORY_ENCRYPTION_KEY` to a valid Fernet key to encrypt newly saved memory content at rest. Keep this key outside source control; losing it makes encrypted memory unreadable. Existing plaintext rows can be migrated by exporting, enabling the key, and re-saving or using a future migration command.

Set `MEMORY_RETENTION_DAYS` to a positive value to delete memories older than the configured number of days during store initialization. Set it to `0` to disable automatic expiration.

The Memory panel is available from the upper-right **Memory** button or the `M` keyboard shortcut. It shows approved and pending records, supports approval and deletion, and provides reindex and JSON export actions.

## Configuration

```env
ENABLE_MEMORY=true
MEMORY_DB_PATH=data/elysia_memory.db
MEMORY_MAX_RESULTS=3
MEMORY_MAX_CONTENT_LENGTH=1000
MEMORY_EMBEDDING_PROVIDER=ollama
MEMORY_EMBEDDING_MODEL=nomic-embed-text
MEMORY_EMBEDDING_TIMEOUT_MS=750
MEMORY_EMBEDDING_PREWARM=true
MEMORY_EMBEDDING_VERSION=nomic-embed-text-v1
MEMORY_ENCRYPTION_KEY=
MEMORY_RETENTION_DAYS=0
ENABLE_PREFERENCE_EXTRACTION=true
```

The memory store currently scans a bounded SQLite set of up to 250 rows per scope and reranks them in process. A dedicated approximate-nearest-neighbor index may be appropriate for very large memory collections, but the current bounded approach preserves simple local response latency and keeps the system dependency-light.
