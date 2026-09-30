# Elysia Tool Calling

Phase 3 adds a fast local tool router before normal LLM generation. High-confidence commands are handled without an additional LLM routing call; ordinary conversational messages continue through the configured local model path.

## Tool catalog

| Tool | Behavior | Confirmation |
|---|---|---|
| `get_current_time` | Returns local time | No |
| `get_system_info` | Returns basic host information | No |
| `get_world_news` | Fetches current world headlines | No |
| `get_world_finance_news` | Fetches current finance headlines | No |
| `fetch_url` | Fetches raw URL text | No |
| `launch_application` | Opens an allowlisted Windows application | Required |
| `search_local_files` | Searches configured local roots by filename or text content | No |
| `summarize_local_document` | Summarizes one bounded local text document with the configured model; Ollama keeps it local | No |
| `list_reminders` | Lists pending local reminders | No |
| `create_reminder` | Persists a local Windows reminder | Required |
| `cancel_reminder` | Cancels one pending local reminder | Required |
| `draft_text` | Creates unsent text from an instruction | No |

The launcher allowlist contains Calculator, Notepad, File Explorer, and Visual Studio Code. Arbitrary shell commands and arbitrary executable paths are not accepted. File tools search only `TOOLS_FILE_ROOTS`; when blank, the default roots are the current user’s Desktop, Documents, and Downloads. Searches skip common build and dependency directories and return bounded results.

## Chat commands

The deterministic router recognizes commands such as `what time is it`, `show system info`, `world news`, and `open calculator`. Phase 3 also supports high-confidence patterns such as `search files for project notes`, `search my files containing invoice`, `summarize C:\Users\Aarya\Documents\notes.txt`, `draft a short thank-you note`, `list reminders`, `remind me to stretch in 10 minutes`, and `cancel reminder 3`.

Reminder creation accepts relative minutes or an ISO-8601 due time. Natural-language dates that are ambiguous are intentionally not auto-parsed; the assistant should ask for a precise time rather than silently scheduling the wrong reminder.

A routed response includes a structured `tool_result` object. Streaming clients receive a `tool` SSE event followed by the normal `done` event. The frontend overlay displays concise summaries, generated drafts, reminder messages, and file-match counts.

## Confirmation and privacy

A risky or persistent command first returns `confirmation_required`. To approve it through the API, resend the same request with `confirm_tool: true`:

```json
{
  "message": "remind me to stretch in 10 minutes",
  "stream": true,
  "confirm_tool": true
}
```

The direct tool API uses the same confirmation flag:

```http
POST /api/v1/tools/create_reminder
Content-Type: application/json

{"arguments":{"title":"Stretch","due_at":"2026-08-20T09:30:00+05:30"},"confirmed":true}
```

Drafts are explicitly unsent. The draft tool only returns text to the local assistant and does not call email, messaging, or browser services. Reminder records are stored in local SQLite at `REMINDER_DB_PATH`. The backend’s local worker checks due records periodically and uses a Windows session notification; failed delivery leaves the reminder pending for a later retry. Document summarization uses the configured LLM: with Ollama selected, the bounded document excerpt remains on the computer; selecting a cloud provider sends that excerpt according to the provider configuration.

Tool audit entries are local append-only JSON lines. Sensitive values such as paths, search queries, reminder titles, due times, and draft instructions are redacted; the audit log retains timestamp, tool name, status, and result status only.

## Configuration

```env
TOOLS_FILE_ROOTS=
TOOLS_MAX_RESULTS=20
TOOLS_MAX_FILE_BYTES=1000000
TOOLS_MAX_SUMMARY_CHARS=12000
TOOLS_MAX_DRAFT_CHARS=2000
TOOLS_EXCLUDED_DIRS=.git,node_modules,.venv,venv,__pycache__
REMINDER_DB_PATH=data/elysia_reminders.db
REMINDER_POLL_SECONDS=15
REMINDER_WORKER_ENABLED=true
```

## Direct tool API

List tools:

```http
GET /api/v1/tools/
```

Execute a tool:

```http
POST /api/v1/tools/search_local_files
Content-Type: application/json

{"arguments":{"query":"project notes","mode":"name"},"confirmed":false}
```

All direct executions pass through the same registry, confirmation policy, error handling, and local audit logging used by chat routing.

## Phase 5 desktop tools

Phase 5 adds bounded Windows desktop tools through the same registry and direct API. Read-only tools such as `list_windows`, `get_active_window`, `read_desktop_file`, `read_clipboard`, and `network_status` do not require confirmation. Window changes, file writes/moves/deletion, clipboard replacement, and keyboard or mouse input are confirmation-gated. Keyboard and mouse automation also require the explicit `DESKTOP_INPUT_ENABLED=true` opt-in.

File operations use `DESKTOP_SAFE_ROOTS` and reject traversal or symlinks. Deletion moves files into `DESKTOP_TRASH_PATH` with a restore token rather than permanently deleting them. Sensitive paths, clipboard text, and input content are redacted in the audit log. No arbitrary shell commands or unrestricted executable paths are accepted.

## Phase 6 browser foundation tools

The browser foundation adds `navigate_browser`, `browser_session_info`, `scrape_browser_page`, and `close_browser_session`. Navigation is disabled until `BROWSER_ALLOWED_DOMAINS` contains an explicit trusted domain. The default scheme is HTTPS, private and IP-literal targets are rejected, redirects are revalidated, and sessions are isolated and non-persistent.

The read-only browser API is also available under `/api/v1/browser`. It returns bounded metadata and visible page content only. It does not return cookies, credentials, hidden form values, scripts, raw HTML, or browser storage state. Clicks, form submission, downloads, screenshots, login persistence, purchases, CAPTCHA bypass, and bot-detection evasion are not part of the foundation milestone.

## Phase 7 code-assistant foundation tools

The code foundation adds `index_code_repository`, `analyze_code_repository`, `search_code_repository`, and `code_repository_status`. Repository analysis is disabled until `CODE_REPOSITORY_ROOTS` contains an explicit trusted local project root. Indexing is metadata-only, excludes dependency and generated directories, rejects symlinks and outside paths, and never executes project code.

The API is available under `/api/v1/code`. The current milestone supports path, symbol, and bounded source-text search plus static project analysis. Code generation, refactoring, patch application, test execution, and arbitrary shell commands are not enabled until a separate preview, recovery, and confirmation workflow is implemented.

## Phase 8 planning foundation

Phase 8 adds local structured plans with dependency validation and lifecycle controls. The planning API is available under `/api/v1/plan`. Plans remain drafts until explicitly approved, and approval does not authorize every task side effect. The execution endpoint currently prepares the next task and returns `confirmation_required` for external side effects; it does not silently execute them.

Plan data and redacted plan events remain in the local SQLite database configured by `PLAN_DB_PATH`. Cyclic graphs, unknown dependencies, disallowed action classes, oversized plans, and unsafe high-impact tasks are rejected. The desktop shell exposes saved plan status and task states through the `Plans · L` panel.

## Phase 9 autonomous-agent foundation

Phase 9 adds local autonomous-agent lifecycle and scheduling controls under `/api/v1/agents`. Agents have explicit tool, plugin, domain, and root allowlists, bounded schedules, per-run and daily budgets, persistent lifecycle state, and a global emergency stop. The local worker prepares due runs but does not execute arbitrary tools or bypass existing confirmations.

The desktop shell exposes agent status through the **Agents · A** panel. Agent configuration and events remain local in the SQLite database configured by `AGENTS_DB_PATH`. A stopped or emergency-paused agent cannot create new runs, and budget exhaustion blocks further preparation until user review.
