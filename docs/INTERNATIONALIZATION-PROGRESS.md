# Internationalization Progress Report

**Initiative:** Post-Phase 12 Continuous Evolution — Internationalization  
**Milestone:** Local language resources and desktop locale selection  
**Status:** Foundation implemented

## Implemented

Elsyia now includes bundled translation resources for English, Hindi, Spanish, French, and German. The main desktop shell translates navigation controls, accessibility labels, tool status messages, and the keyboard-hint bar. A language panel is available from the `I` shortcut or the locale button in the upper-left corner.

The selected locale is persisted only in local browser/Electron storage. No cloud call, LLM request, account synchronization, or external analytics event is used for language selection. Unsupported browser locales fall back to English. Missing translation keys fall back to the English resource and finally to the key itself.

The localization utility also provides locale-aware date and number formatting through the browser's `Intl` APIs. The current shell explicitly maintains left-to-right layout because all initial locales use that layout; right-to-left support remains a future milestone.

## Supported locales

| Code | Language | Resource status |
|---|---|---|
| `en` | English | Canonical complete shell resource |
| `hi` | Hindi | Main shell resource |
| `es` | Spanish | Main shell resource with English fallback for unspecified strings |
| `fr` | French | Main shell resource with English fallback for unspecified strings |
| `de` | German | Main shell resource with English fallback for unspecified strings |

## Verification

The localization regression checks passed. They verify the locale resource set, stable translation keys, English fallback, unsupported-locale fallback, local persistence, locale-aware formatting, language-panel integration, and the `I` shortcut. The frontend TypeScript and production build also passed; Vite emitted only the existing large-chunk advisory.

## Remaining work

The remaining localization scope is translating the Memory, Plugins, Plans, Agents, Sync, Admin, and Drop Zone panels; reviewing translations with native speakers; adding locale-aware formatting to panel timestamps and counts; supporting right-to-left layout where required; adding pluralization and accessibility-language metadata; and defining an explicit, confirmed translation action for user-provided content. User content is not automatically translated by this milestone.
