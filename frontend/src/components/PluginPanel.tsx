import { useCallback, useEffect, useState } from "react";
import { apiBase } from "../lib/api";

const API_BASE = apiBase();

interface PluginInfo {
  id: string;
  name: string;
  version: string;
  description: string;
  state: string;
  permissions: string[];
  requires_confirmation: boolean;
  error?: string | null;
}

interface PluginPanelProps {
  open: boolean;
  onClose: () => void;
}

export default function PluginPanel({ open, onClose }: PluginPanelProps) {
  const [plugins, setPlugins] = useState<PluginInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmingId, setConfirmingId] = useState<string | null>(null);

  const loadPlugins = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/plugins`);
      if (!response.ok) throw new Error(`Plugin catalog failed: ${response.status}`);
      const payload = (await response.json()) as { plugins: PluginInfo[] };
      setPlugins(payload.plugins);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not load plugins");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) void loadPlugins();
  }, [open, loadPlugins]);

  const togglePlugin = async (plugin: PluginInfo, confirmed = false) => {
    setError(null);
    try {
      const action = plugin.state === "enabled" ? "disable" : "enable";
      const response = await fetch(`${API_BASE}/plugins/${plugin.id}/${action}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirmed }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "Plugin action failed");
      if (payload.status === "confirmation_required") {
        setConfirmingId(plugin.id);
        return;
      }
      setConfirmingId(null);
      await loadPlugins();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Plugin action failed");
    }
  };

  if (!open) return null;

  return (
    <aside className="fixed right-5 top-16 z-20 w-[min(360px,calc(100vw-2.5rem))] rounded-2xl border border-cyan-200/15 bg-slate-950/95 p-4 text-cyan-50 shadow-2xl backdrop-blur-xl">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-[0.18em]">Plugins</h2>
          <p className="mt-1 text-[10px] uppercase tracking-[0.14em] text-cyan-100/45">Trusted local extensions</p>
        </div>
        <button onClick={onClose} className="rounded-lg px-2 py-1 text-xs text-cyan-100/60 hover:bg-cyan-300/10" aria-label="Close plugins">
          Close
        </button>
      </div>
      {loading && <p className="text-xs text-cyan-100/60">Loading plugin catalog…</p>}
      {error && <p className="rounded-lg bg-red-400/10 p-2 text-xs text-red-200">{error}</p>}
      {!loading && plugins.length === 0 && <p className="text-xs text-cyan-100/60">No local plugins discovered.</p>}
      <div className="max-h-[55vh] space-y-2 overflow-y-auto pr-1">
        {plugins.map((plugin) => (
          <div key={`${plugin.id}-${plugin.state}`} className="rounded-xl border border-cyan-100/10 bg-cyan-100/[0.03] p-3">
            <div className="flex items-start justify-between gap-2">
              <div>
                <p className="text-xs font-medium">{plugin.name}</p>
                <p className="mt-1 text-[10px] text-cyan-100/45">v{plugin.version} · {plugin.state}</p>
              </div>
              <button
                onClick={() => void togglePlugin(plugin, confirmingId === plugin.id)}
                className="rounded-lg border border-cyan-200/15 px-2 py-1 text-[10px] uppercase tracking-[0.12em] text-cyan-100/75 hover:bg-cyan-300/10"
              >
                {confirmingId === plugin.id ? "Confirm" : plugin.state === "enabled" ? "Disable" : "Enable"}
              </button>
            </div>
            <p className="mt-2 text-xs leading-relaxed text-cyan-50/65">{plugin.description}</p>
            {plugin.permissions.length > 0 && (
              <p className="mt-2 text-[10px] text-amber-200/70">Permissions: {plugin.permissions.join(", ")}</p>
            )}
            {plugin.error && <p className="mt-2 text-[10px] text-red-200/80">{plugin.error}</p>}
          </div>
        ))}
      </div>
    </aside>
  );
}
