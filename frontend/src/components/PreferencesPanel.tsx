import { useEffect, useState } from "react";

type Preferences = {
  reducedMotion: boolean;
  highContrast: boolean;
  compactLayout: boolean;
};

const KEY = "elysia-preferences";
const DEFAULTS: Preferences = { reducedMotion: false, highContrast: false, compactLayout: false };

function load(): Preferences {
  try {
    return { ...DEFAULTS, ...JSON.parse(localStorage.getItem(KEY) || "{}") };
  } catch {
    return DEFAULTS;
  }
}

export default function PreferencesPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [preferences, setPreferences] = useState<Preferences>(load);

  useEffect(() => {
    document.documentElement.dataset.reducedMotion = preferences.reducedMotion ? "true" : "false";
    document.documentElement.dataset.highContrast = preferences.highContrast ? "true" : "false";
    document.documentElement.dataset.compactLayout = preferences.compactLayout ? "true" : "false";
    localStorage.setItem(KEY, JSON.stringify(preferences));
  }, [preferences]);

  if (!open) return null;
  const toggle = (key: keyof Preferences) => setPreferences((current) => ({ ...current, [key]: !current[key] }));
  return (
    <aside className="fixed left-5 top-16 z-20 w-72 rounded-2xl border border-cyan-200/20 bg-slate-950/95 p-4 text-cyan-50 shadow-2xl backdrop-blur" role="dialog" aria-modal="true" aria-labelledby="preferences-title">
      <div className="mb-3 flex items-center justify-between">
        <h2 id="preferences-title" className="text-sm font-semibold tracking-wide">Preferences</h2>
        <button onClick={onClose} className="rounded px-2 py-1 text-xs text-cyan-100/70 hover:bg-cyan-300/10" aria-label="Close preferences">Close</button>
      </div>
      <p className="mb-4 text-xs leading-5 text-cyan-100/60">Stored locally on this computer. These settings do not contact a remote service.</p>
      <div className="space-y-2 text-xs">
        {(["reducedMotion", "highContrast", "compactLayout"] as const).map((key) => (
          <label key={key} className="flex cursor-pointer items-center justify-between rounded-lg border border-cyan-100/10 px-3 py-2 hover:bg-cyan-300/5">
            <span>{key === "reducedMotion" ? "Reduce motion" : key === "highContrast" ? "High contrast" : "Compact layout"}</span>
            <input type="checkbox" checked={preferences[key]} onChange={() => toggle(key)} aria-label={key} />
          </label>
        ))}
      </div>
    </aside>
  );
}
