import { useCallback, useEffect, useState } from "react";

type Agent = {
  id: string;
  name: string;
  purpose: string;
  status: string;
  allowed_tools: string[];
  interval_seconds: number | null;
  runs_used: number;
  max_runs: number;
  last_error?: string | null;
};

const API = "http://127.0.0.1:8000/api/v1";

export default function AgentPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [stopped, setStopped] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const response = await fetch(`${API}/agents`);
      if (!response.ok) throw new Error("Could not load agents");
      const payload = await response.json();
      setAgents(payload.agents || []);
      setStopped(Boolean(payload.emergency_stop));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load agents");
    }
  }, []);

  const action = useCallback(async (path: string, method = "POST", body?: unknown) => {
    setError(null);
    try {
      const response = await fetch(`${API}${path}`, {
        method,
        headers: body ? { "Content-Type": "application/json" } : undefined,
        body: body ? JSON.stringify(body) : undefined,
      });
      const payload = await response.json();
      if (!response.ok || payload.status === "failed") throw new Error(payload.error || "Agent action failed");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Agent action failed");
    }
  }, [refresh]);

  useEffect(() => {
    if (open) void refresh();
  }, [open, refresh]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-20 flex items-start justify-end bg-black/35 p-5 backdrop-blur-sm">
      <section className="max-h-[calc(100vh-2.5rem)] w-full max-w-md overflow-y-auto rounded-2xl border border-cyan-200/15 bg-slate-950/95 p-5 text-cyan-50 shadow-2xl">
        <div className="mb-5 flex items-center justify-between">
          <div>
            <h2 className="text-sm uppercase tracking-[0.25em] text-cyan-100">Agents</h2>
            <p className="mt-1 text-[11px] text-cyan-100/50">Bounded background preparation and lifecycle control</p>
          </div>
          <div className="flex gap-2">
            <button onClick={() => void refresh()} className="rounded-lg border border-cyan-200/15 px-2 py-1 text-[10px] uppercase tracking-widest text-cyan-100/70 hover:bg-cyan-300/10">Refresh</button>
            <button onClick={onClose} className="rounded-lg border border-cyan-200/15 px-2 py-1 text-[10px] uppercase tracking-widest text-cyan-100/70 hover:bg-cyan-300/10">Close</button>
          </div>
        </div>
        <div className="mb-4 flex items-center justify-between rounded-xl border border-red-300/15 bg-red-950/20 p-3">
          <div>
            <div className="text-xs uppercase tracking-widest text-red-100/80">Emergency stop</div>
            <div className="mt-1 text-[10px] text-red-100/50">{stopped ? "Active: new runs are blocked" : "Inactive"}</div>
          </div>
          <button
            onClick={() => void action(stopped ? "/agents/emergency-stop/clear" : "/agents/emergency-stop")}
            className="rounded-lg border border-red-200/20 px-2 py-1 text-[10px] uppercase tracking-widest text-red-100/80 hover:bg-red-300/10"
          >
            {stopped ? "Clear" : "Stop all"}
          </button>
        </div>
        {error && <p className="mb-3 rounded-lg bg-red-950/40 p-2 text-xs text-red-200">{error}</p>}
        {agents.length === 0 && <p className="text-xs text-cyan-100/50">No agents have been created yet.</p>}
        <div className="space-y-3">
          {agents.map((agent) => (
            <div key={agent.id} className="rounded-xl border border-cyan-200/10 bg-white/[0.03] p-3">
              <div className="flex items-center justify-between gap-3">
                <span className="text-xs text-cyan-50">{agent.name}</span>
                <span className="text-[10px] uppercase tracking-widest text-cyan-200/60">{agent.status}</span>
              </div>
              <p className="mt-2 text-xs leading-5 text-cyan-100/60">{agent.purpose}</p>
              <div className="mt-2 text-[10px] text-cyan-100/40">{agent.allowed_tools.length} tools · {agent.runs_used}/{agent.max_runs} runs{agent.interval_seconds ? ` · every ${agent.interval_seconds}s` : ""}</div>
              {agent.last_error && <div className="mt-2 text-[10px] text-red-200/70">{agent.last_error}</div>}
              <div className="mt-3 flex gap-2">
                <button onClick={() => void action(`/agents/${agent.id}/start`)} className="rounded-lg border border-cyan-200/15 px-2 py-1 text-[10px] uppercase tracking-widest text-cyan-100/70 hover:bg-cyan-300/10">Start</button>
                <button onClick={() => void action(`/agents/${agent.id}/run`, "POST", { force: true })} className="rounded-lg border border-cyan-200/15 px-2 py-1 text-[10px] uppercase tracking-widest text-cyan-100/70 hover:bg-cyan-300/10">Prepare run</button>
                <button onClick={() => void action(`/agents/${agent.id}/stop`)} className="rounded-lg border border-cyan-200/15 px-2 py-1 text-[10px] uppercase tracking-widest text-cyan-100/70 hover:bg-cyan-300/10">Stop</button>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
