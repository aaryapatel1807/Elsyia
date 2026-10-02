"""Static regression checks for the local internationalization foundation."""

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
i18n = (ROOT / "frontend/src/i18n.ts").read_text(encoding="utf-8")
app = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
panel = (ROOT / "frontend/src/components/LanguagePanel.tsx").read_text(encoding="utf-8")

def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)

check("const en: Messages" in i18n, "missing locale resource: en")
for locale in ("hi", "es", "fr", "de"):
    check(f"{locale}: {{" in i18n, f"missing locale resource: {locale}")

for key in ("app.memory", "app.plugins", "app.plans", "app.agents", "app.sync", "app.admin", "language.select"):
    check(f'"{key}"' in i18n, f"missing translation key: {key}")

check('const STORAGE_KEY = "elysia.locale"' in i18n, "locale persistence key missing")
check("resources.en[key]" in i18n, "English fallback missing")
check("return \"en\"" in i18n, "unsupported-locale fallback missing")
check("Intl.DateTimeFormat" in i18n and "Intl.NumberFormat" in i18n, "locale-aware formatting missing")
check("LanguagePanel" in app and "elysia-locale-change" in app, "main-shell locale integration missing")
check("I FOR LANGUAGE" in app, "language shortcut hint missing")
check("supportedLocales.map" in panel, "language selector missing locale list")
check("localStorage" in i18n, "local-only persistence missing")

print("i18n regression checks passed")
