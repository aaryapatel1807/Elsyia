import { useCallback, useEffect, useState } from "react";

const API_BASE = "http://127.0.0.1:8000/api/v1";

type Memory = {
  id: string;
  content: string;
  category: string;
  source: string;
  created_at: string;
  approved: boolean;
};

type Stats = {
  total: number;
  pending: number;
  indexed: number;
  encrypted: boolean;
};

type Props = {
  open: boolean;
  onClose: () => void;
};

export default function MemoryPanel({ open, onClose }: Props) {
  const [memories, setMemories] = useState<Memory[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [memoryResponse, statsResponse] = await Promise.all([
        fetch(`${API_BASE}/memory/?scope=default&include_pending=true`),
        fetch(`${API_BASE}/memory/stats?scope=default`),
      ]);
      if (!memoryResponse.ok || !statsResponse.ok) throw new Error("Memory service unavailable");
      const memoryData = await memoryResponse.json();
      const statsData = await statsResponse.json();
      setMemories(memoryData.memories || []);
      setStats(statsData);
      setMessage(null);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not load memories");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) void load();
  }, [open, load]);

  const approve = async (id: string) => {
    const response = await fetch(`${API_BASE}/memory/${id}/approve?scope=default`, { method: "POST" });
    setMessage(response.ok ? "Memory approved" : "Could not approve that memory");
    void load();
  };

  const remove = async (id: string) => {
    const response = await fetch(`${API_BASE}/memory/${id}?scope=default`, { method: "DELETE" });
    if (!response.ok) {
      setMessage("Could not delete that memory");
      return;
    }
    setMessage("Memory deleted");
    void load();
  };

  const clearAll = async () => {
    if (!window.confirm("Delete all saved memories in the default scope?")) return;
    const response = await fetch(`${API_BASE}/memory/?scope=default`, { method: "DELETE" });
    if (!response.ok) {
      setMessage("Could not clear memories");
      return;
    }
    setMessage("All memories cleared");
    void load();
  };

  const reindex = async () => {
    setMessage("Rebuilding memory vectors…");
    const response = await fetch(`${API_BASE}/memory/reindex`, { method: "POST" });
    setMessage(response.ok ? "Memory vectors rebuilt" : "Reindex failed");
    void load();
  };

  const exportMemories = async () => {
    const response = await fetch(`${API_BASE}/memory/export?scope=default`);
    if (!response.ok) {
      setMessage("Export failed");
      return;
    }
    const data = await response.json();
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "elysia-memories.json";
    anchor.click();
    URL.revokeObjectURL(url);
    setMessage("Memory export downloaded");
  };

  if (!open) return null;

  return (
    <aside className="fixed right-5 top-5 z-20 h-[calc(100vh-40px)] w-[min(420px,calc(100vw-40px))] overflow-hidden rounded-2xl border border-cyan-200/15 bg-slate-950/90 p-5 text-slate-100 shadow-2xl shadow-cyan-950/30 backdrop-blur-xl">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-[10px] uppercase tracking-[0.3em] text-cyan-300/70">Private local context</p>
          <h2 className="mt-1 text-xl font-medium">Memory</h2>
          <p className="mt-1 text-xs leading-5 text-slate-400">Review what Elysia can remember. Everything here stays on this computer.</p>
        </div>
        <button onClick={onClose} className="rounded-lg px-2 py-1 text-slate-400 hover:bg-white/10 hover:text-white" aria-label="Close memory panel">×</button>
      </div>

      <div className="mt-4 grid grid-cols-3 gap-2 text-center text-[11px]">
        <div className="rounded-xl border border-white/10 bg-white/5 p-2"><strong className="block text-base text-cyan-200">{stats?.total ?? 0}</strong>saved</div>
        <div className="rounded-xl border border-white/10 bg-white/5 p-2"><strong className="block text-base text-cyan-200">{stats?.pending ?? 0}</strong>pending</div>
        <div className="rounded-xl border border-white/10 bg-white/5 p-2"><strong className="block text-base text-cyan-200">{stats?.encrypted ? "On" : "Off"}</strong>encryption</div>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <button onClick={() => void reindex()} className="rounded-lg border border-cyan-300/20 px-3 py-2 text-[11px] text-cyan-100 hover:bg-cyan-300/10">Reindex</button>
        <button onClick={() => void exportMemories()} className="rounded-lg border border-white/10 px-3 py-2 text-[11px] text-slate-200 hover:bg-white/10">Export</button>
        <button onClick={() => void clearAll()} className="rounded-lg border border-red-300/20 px-3 py-2 text-[11px] text-red-200 hover:bg-red-300/10">Clear all</button>
      </div>

      {message && <p className="mt-3 text-xs text-cyan-200/80">{message}</p>}
      <div className="mt-4 h-[calc(100%-190px)] overflow-y-auto pr-1">
        {loading ? <p className="text-sm text-slate-400">Loading memories…</p> : memories.length === 0 ? <p className="text-sm text-slate-400">No saved memories yet.</p> : memories.map((memory) => (
          <article key={memory.id} className="mb-2 rounded-xl border border-white/10 bg-white/[0.04] p-3">
            <div className="flex items-start justify-between gap-3">
              <p className="text-sm leading-5 text-slate-100">{memory.content}</p>
              <div className="flex shrink-0 gap-2 text-xs">
                {!memory.approved && <button onClick={() => void approve(memory.id)} className="text-cyan-200/80 hover:text-cyan-100">Approve</button>}
                <button onClick={() => void remove(memory.id)} className="text-red-200/70 hover:text-red-100" aria-label={`Delete memory: ${memory.content}`}>Delete</button>
              </div>
            </div>
            <p className="mt-2 text-[10px] uppercase tracking-wider text-slate-500">{memory.category} · {memory.source} · {memory.approved ? "approved" : "needs review"}</p>
          </article>
        ))}
      </div>
    </aside>
  );
}
