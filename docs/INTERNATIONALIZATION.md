# Internationalization and Localization Foundation

**Initiative:** Post-Phase 12 Continuous Evolution — Internationalization  
**Milestone:** Local language resources and desktop locale selection  
**Status:** In progress

## Scope

This milestone localizes the main desktop shell and establishes reusable translation utilities. Translation resources are bundled with the frontend, so changing language does not call a cloud service, send user text externally, or depend on model inference.

The initial locale set is English (`en`), Hindi (`hi`), Spanish (`es`), French (`fr`), and German (`de`). English is the canonical source locale and the fallback for missing keys or unsupported locale values. User-selected locale is stored in browser/Electron local storage only.

## Translation contract

Translations use stable dotted keys and optional `{placeholder}` interpolation. Missing keys fall back first to English and then to the key itself. Resource values must remain bounded UI strings; conversation content, model output, tool results, and user-provided files are not automatically translated by this foundation.

| Rule | Behavior |
|---|---|
| Default locale | English (`en`) |
| Supported locales | `en`, `hi`, `es`, `fr`, `de` |
| Fallback | Selected locale → English → key |
| Persistence | Local storage only; no account sync |
| Formatting | `Intl.DateTimeFormat` and `Intl.NumberFormat` using selected locale |
| Cloud dependency | None |
| Model dependency | None |
| User content | Remains unchanged unless a future explicit translation action is requested |

## Future work

The next localization milestones are translating the remaining panels, adding locale-aware accessibility labels and date/number formatting throughout the UI, providing right-to-left layout support where needed, and adding human-reviewed resources for additional languages. Automatic translation of user content requires an explicit action, confirmation, bounded payload, and a separately selected local or cloud provider.
