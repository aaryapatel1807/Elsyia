import { useCallback, useEffect, useState } from "react";
import { apiBase } from "../lib/api";

const API_BASE = apiBase();

type Backup = {
  id: string;
  filename: string;
  size_bytes: number;
  digest_prefix: string;
  sequence: number;
  device_id: string;
  created_at: string;
  status: string;
};

type Status = {
  enabled: boolean;
  cloud_enabled: boolean;
  cloud_configured: boolean;
  device_id: string;
  backup_count: number;
  latest_sequence: number | null;
};

type Preview = {
  backup_id: string;
  device_id: string;
  sequence: number;
  created_at: string;
  files: Array<{ key: string; state: string; size_bytes: number }>;
  conflicts: string[];
  requires_confirmation: boolean;
};

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function SyncPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [backups, setBackups] = useState<Backup[]>([]);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [statusResponse, backupResponse] = await Promise.all([
        fetch(`${API_BASE}/sync/status`),
        fetch(`${API_BASE}/sync/backups`),
      ]);
      if (!statusResponse.ok || !backupResponse.ok) throw new Error("Sync status unavailable");
      setStatus((await statusResponse.json()) as Status);
      setBackups(((await backupResponse.json()) as { backups: Backup[] }).backups);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not load sync status.");
    }
  }, []);

  useEffect(() => {
    if (open) void refresh();
  }, [open, refresh]);

  const createBackup = async () => {
    setBusy(true);
    setMessage(null);
    try {
      const response = await fetch(`${API_BASE}/sync/backup`, { method: "POST" });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || "Backup creation failed.");
      setMessage(`Encrypted backup ${data.sequence} created locally.`);
      await refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Backup creation failed.");
    } finally {
      setBusy(false);
    }
  };

  const previewRestore = async (backupId: string) => {
    setBusy(true);
    setMessage(null);
    try {
      const response = await fetch(`${API_BASE}/sync/restore/preview`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ backup_id: backupId }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || "Restore preview failed.");
      setPreview(data as Preview);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Restore preview failed.");
    } finally {
      setBusy(false);
    }
  };

  const restore = async (force: boolean) => {
    if (!preview) return;
    if (!window.confirm("Restore this backup? Existing local databases will be copied to a safety folder first.")) return;
    setBusy(true);
    try {
      const response = await fetch(`${API_BASE}/sync/restore`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ backup_id: preview.backup_id, confirm: true, force }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || "Restore failed.");
      setMessage(`Restored ${data.restored} databases. Safety copy: ${data.safety_backup}`);
      setPreview(null);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Restore failed.");
    } finally {
      setBusy(false);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-y-0 right-0 z-30 w-[min(92vw,28rem)] border-l border-cyan-200/15 bg-slate-950/95 p-5 text-cyan-50 shadow-2xl backdrop-blur-xl">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-[10px] uppercase tracking-[0.22em] text-cyan-100/60">Phase 11</p>
          <h2 className="mt-1 text-lg font-light tracking-wide">Local Sync</h2>
        </div>
        <button type="button" onClick={onClose} className="text-sm text-cyan-100/60 hover:text-cyan-50">Close</button>
      </div>

      <div className="mt-5 rounded-xl border border-cyan-200/10 bg-cyan-950/20 p-3 text-xs text-cyan-100/75">
        <p>Device: <span className="text-cyan-50">{status?.device_id || "loading…"}</span></p>
        <p className="mt-1">Cloud transport: <span className="text-amber-100">{status?.cloud_enabled ? "enabled by configuration" : "disabled"}</span></p>
        <p className="mt-1">Encrypted local backups: <span className="text-cyan-50">{status?.backup_count ?? 0}</span></p>
      </div>

      <button
        type="button"
        onClick={() => void createBackup()}
        disabled={busy}
        className="mt-4 w-full rounded-xl border border-cyan-200/20 bg-cyan-300/10 px-4 py-3 text-xs uppercase tracking-[0.16em] text-cyan-50 hover:bg-cyan-300/20 disabled:opacity-40"
      >
        {busy ? "Working…" : "Create encrypted backup"}
      </button>

      {message && <p className="mt-3 text-xs text-cyan-100/70">{message}</p>}

      <div className="mt-5 space-y-2 overflow-y-auto">
        {backups.map((backup) => (
          <div key={backup.id} className="rounded-xl border border-cyan-200/10 bg-slate-900/70 p-3">
            <div className="flex items-center justify-between gap-2 text-xs">
              <span>Backup {backup.sequence}</span>
              <span className="text-cyan-100/45">{formatBytes(backup.size_bytes)}</span>
            </div>
            <p className="mt-1 truncate text-[11px] text-cyan-100/45">{backup.filename}</p>
            <p className="mt-1 text-[10px] text-cyan-100/35">Digest {backup.digest_prefix} · {new Date(backup.created_at).toLocaleString()}</p>
            <button
              type="button"
              onClick={() => void previewRestore(backup.id)}
              disabled={busy}
              className="mt-2 rounded-lg border border-cyan-200/15 px-2 py-1 text-[10px] uppercase tracking-[0.12em] text-cyan-100/70 hover:bg-cyan-300/10 disabled:opacity-40"
            >
              Preview restore
            </button>
          </div>
        ))}
      </div>

      {preview && (
        <div className="mt-5 rounded-xl border border-amber-200/20 bg-amber-950/20 p-3 text-xs">
          <p className="uppercase tracking-[0.14em] text-amber-100/80">Restore preview</p>
          <div className="mt-2 space-y-1 text-amber-50/75">
            {preview.files.map((file) => <p key={file.key}>{file.key}: {file.state} · {formatBytes(file.size_bytes)}</p>)}
          </div>
          {preview.conflicts.length > 0 && <p className="mt-2 text-red-200/80">Conflicts: {preview.conflicts.join(", ")}</p>}
          <div className="mt-3 flex gap-2">
            <button type="button" onClick={() => void restore(false)} disabled={busy} className="rounded-lg border border-amber-100/20 px-2 py-1 text-[10px] uppercase tracking-[0.1em] text-amber-50 hover:bg-amber-200/10 disabled:opacity-40">Restore</button>
            {preview.conflicts.length > 0 && <button type="button" onClick={() => void restore(true)} disabled={busy} className="rounded-lg border border-red-200/20 px-2 py-1 text-[10px] uppercase tracking-[0.1em] text-red-100 hover:bg-red-200/10 disabled:opacity-40">Force overwrite</button>}
            <button type="button" onClick={() => setPreview(null)} className="rounded-lg border border-cyan-200/15 px-2 py-1 text-[10px] uppercase tracking-[0.1em] text-cyan-100/65">Cancel</button>
          </div>
        </div>
      )}
    </div>
  );
}
