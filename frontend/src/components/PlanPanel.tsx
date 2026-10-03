import { useCallback, useEffect, useState } from "react";
import { apiBase } from "../lib/api";

type PlanSummary = {
  id: string;
  goal: string;
  status: string;
  version: number;
  updated_at: string;
};

type PlanDetail = {
  id: string;
  goal: string;
  status: string;
  version: number;
  tasks: Array<{ id: string; title: string; status: string; action_class: string }>;
  reasoning_summary?: string;
};

const API = apiBase();

export default function PlanPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [plans, setPlans] = useState<PlanSummary[]>([]);
  const [selected, setSelected] = useState<PlanDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API}/plan`);
      if (!response.ok) throw new Error("Could not load plans");
      const payload = await response.json();
      setPlans(payload.plans || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load plans");
    } finally {
      setLoading(false);
    }
  }, []);

  const openPlan = useCallback(async (id: string) => {
    try {
      const response = await fetch(`${API}/plan/${id}`);
      if (!response.ok) throw new Error("Could not load plan details");
      const payload = await response.json();
      setSelected(payload.plan || null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load plan details");
    }
  }, []);

  useEffect(() => {
    if (open) void refresh();
  }, [open, refresh]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-20 flex items-start justify-end bg-black/35 p-5 backdrop-blur-sm">
      <section className="max-h-[calc(100vh-2.5rem)] w-full max-w-md overflow-y-auto rounded-2xl border border-cyan-200/15 bg-slate-950/95 p-5 text-cyan-50 shadow-2xl">
        <div className="mb-5 flex items-center justify-between">
          <div>
            <h2 className="text-sm uppercase tracking-[0.25em] text-cyan-100">Plans</h2>
            <p className="mt-1 text-[11px] text-cyan-100/50">Drafts, approvals, progress, and task safety</p>
          </div>
          <div className="flex gap-2">
            <button onClick={() => void refresh()} className="rounded-lg border border-cyan-200/15 px-2 py-1 text-[10px] uppercase tracking-widest text-cyan-100/70 hover:bg-cyan-300/10">Refresh</button>
            <button onClick={onClose} className="rounded-lg border border-cyan-200/15 px-2 py-1 text-[10px] uppercase tracking-widest text-cyan-100/70 hover:bg-cyan-300/10">Close</button>
          </div>
        </div>
        {loading && <p className="text-xs text-cyan-100/60">Loading plans…</p>}
        {error && <p className="mb-3 rounded-lg bg-red-950/40 p-2 text-xs text-red-200">{error}</p>}
        {!loading && plans.length === 0 && <p className="text-xs text-cyan-100/50">No plans have been created yet.</p>}
        <div className="space-y-2">
          {plans.map((plan) => (
            <button key={plan.id} onClick={() => void openPlan(plan.id)} className="w-full rounded-xl border border-cyan-200/10 bg-white/[0.03] p-3 text-left hover:bg-cyan-300/10">
              <div className="flex items-center justify-between gap-3">
                <span className="line-clamp-2 text-xs text-cyan-50">{plan.goal}</span>
                <span className="shrink-0 text-[10px] uppercase tracking-widest text-cyan-200/60">{plan.status}</span>
              </div>
              <div className="mt-2 text-[10px] text-cyan-100/40">v{plan.version} · {new Date(plan.updated_at).toLocaleString()}</div>
            </button>
          ))}
        </div>
        {selected && (
          <div className="mt-5 rounded-xl border border-cyan-200/10 bg-black/20 p-3">
            <div className="flex items-center justify-between">
              <h3 className="text-xs uppercase tracking-widest text-cyan-100/80">Plan details</h3>
              <span className="text-[10px] uppercase tracking-widest text-cyan-200/60">{selected.status}</span>
            </div>
            {selected.reasoning_summary && <p className="mt-3 text-xs leading-5 text-cyan-100/65">{selected.reasoning_summary}</p>}
            <div className="mt-3 space-y-2">
              {selected.tasks.map((task) => (
                <div key={task.id} className="rounded-lg border border-cyan-200/10 p-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs text-cyan-50">{task.title}</span>
                    <span className="text-[10px] uppercase tracking-widest text-cyan-200/55">{task.status}</span>
                  </div>
                  <div className="mt-1 text-[10px] text-cyan-100/35">{task.action_class}</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
