import { useEffect, useState } from "react";
import { formatDate, getStoredLocale, localeLabels, setStoredLocale, supportedLocales, translate, type Locale } from "@/i18n";

export default function LanguagePanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [locale, setLocale] = useState<Locale>(getStoredLocale());

  useEffect(() => {
    document.documentElement.lang = locale;
    document.documentElement.dir = "ltr";
  }, [locale]);

  if (!open) return null;

  const selectLocale = (value: Locale) => {
    setLocale(value);
    setStoredLocale(value);
    window.dispatchEvent(new CustomEvent("elysia-locale-change", { detail: value }));
  };

  return (
    <aside className="fixed inset-y-0 left-0 z-40 w-[min(92vw,22rem)] border-r border-cyan-200/15 bg-slate-950/95 p-5 text-cyan-50 shadow-2xl backdrop-blur-xl">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-[10px] uppercase tracking-[0.22em] text-cyan-100/60">{translate(locale, "language.title")}</p>
          <h2 className="mt-1 text-lg font-light tracking-wide">{translate(locale, "language.select")}</h2>
        </div>
        <button type="button" onClick={onClose} className="text-sm text-cyan-100/60 hover:text-cyan-50">{translate(locale, "panel.close")}</button>
      </div>
      <div className="mt-5 space-y-2">
        {supportedLocales.map((item) => (
          <button key={item} type="button" onClick={() => selectLocale(item)} className={`flex w-full items-center justify-between rounded-lg border px-3 py-3 text-left text-sm ${locale === item ? "border-cyan-200/40 bg-cyan-300/10" : "border-cyan-200/10 bg-slate-900/70 hover:bg-cyan-300/10"}`}>
            <span>{translate(locale, localeLabels[item])}</span>
            <span className="text-xs uppercase text-cyan-100/45">{item}</span>
          </button>
        ))}
      </div>
      <p className="mt-5 text-xs leading-relaxed text-cyan-100/50">{translate(locale, "language.localOnly")}</p>
      <p className="mt-2 text-[10px] text-cyan-100/35">{formatDate(new Date(), locale)}</p>
    </aside>
  );
}
