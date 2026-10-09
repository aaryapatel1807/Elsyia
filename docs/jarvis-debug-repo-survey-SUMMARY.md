# Elsyia debugging repository survey — summary

**Survey date:** 2026-10-09
**Output file:** `jarvis-debug-repo-survey.csv` (same directory)
**Total distinct repositories:** 1,074

## Per-domain breakdown

| Domain | Rows | Coverage |
|---|---|---|
| Voice AI | 262 | Whisper/STT ecosystem, TTS (Piper/Coqui/MeloTTS), wake-word, VAD, audio DSP/IO, speech toolkits |
| LLM & agents | 266 | Ollama ecosystem, local LLM serving, RAG/vector DBs, agent frameworks, eval, observability, prompt tooling |
| Desktop & frontend | 300 | Electron core/tooling, React/TS ecosystem, overlay widgets, tray/shortcuts, Web Audio, MediaPipe JS, frontend testing |
| Backend, packaging & integrations | 246 | FastAPI/Python, PyInstaller, MSIX/AppX/electron-builder, auto-update, OAuth2/Google APIs, Instagram/social libs, testing/debugging/observability |

## Verification method

Each repository URL was verified with an HTTP HEAD/GET request
(`curl -sIL --max-time 15 https://github.com/<owner>/<repo>`) on 2026-10-09.
Only repositories returning a final HTTP 200 were kept; the recorded URL is the
canonical post-redirect URL, so renamed repositories resolve correctly.
Candidates that 404'd or redirected to non-repo pages were dropped (8 dropped,
7 corrected to their canonical repo paths after re-verification).
No GitHub rate-limit block was hit during verification.

## Honest caveats

- **Existence, not quality, was verified.** A 200 response confirms the repo
  exists and is public; it does not confirm the project is maintained, secure,
  or suitable as a dependency.
- **Stars, license, and freshness are best-effort** values from the surveyors'
  knowledge at survey time, not live API data. Treat them as rough signals.
- **Relevance notes are one-line pointers**, written to connect each repo to a
  concrete Elsyia debugging scenario (e.g. PyInstaller hidden-import crashes,
  Ollama connection failures, AppX capability gaps). They are starting points
  for investigation, not endorsements.
- A few entries are "awesome lists" (curated indexes) rather than code
  projects; they are included deliberately as discovery aids.
- The survey reflects the public GitHub state on 2026-10-09; repositories may
  since have been renamed, archived, or deleted.
