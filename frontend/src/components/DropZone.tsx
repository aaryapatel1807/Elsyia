import { useCallback, useEffect, useRef, useState } from "react";
import { apiBase } from "../lib/api";

const API_BASE = apiBase();

type ProcessingJob = {
  id: string;
  status: "queued" | "running" | "completed" | "failed";
  summary: string | null;
  error: string | null;
  memory_proposal_ids: string[];
  extracted_chars: number;
  truncated: boolean;
};

type Attachment = {
  token: string;
  event_id: string;
  display_name: string;
  extension: string;
  size_bytes: number;
  mime_type: string;
  digest_prefix: string;
  kind: string;
  expires_at: string;
  status: string;
  processing_job?: ProcessingJob | null;
};

type PathFile = File & { path?: string };

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function DropZone() {
  const [isOver, setIsOver] = useState(false);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const loadAttachments = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/input/attachments`);
      if (!response.ok) throw new Error("Attachment list unavailable");
      const data = (await response.json()) as { attachments: Attachment[] };
      setAttachments(data.attachments);
    } catch {
      // The backend may still be starting; the drop zone remains usable once it is ready.
    }
  }, []);

  useEffect(() => {
    void loadAttachments();
  }, [loadAttachments]);

  useEffect(() => {
    const hasActiveJobs = attachments.some(
      (attachment) => attachment.processing_job?.status === "queued" || attachment.processing_job?.status === "running",
    );
    if (!hasActiveJobs) return;
    const timer = window.setInterval(() => void loadAttachments(), 2000);
    return () => window.clearInterval(timer);
  }, [attachments, loadAttachments]);

  const ingest = useCallback(async (files: FileList | File[]) => {
    const selected = Array.from(files);
    if (!selected.length) return;
    const paths = selected
      .map((file) => (file as PathFile).path)
      .filter((path): path is string => Boolean(path));
    if (paths.length !== selected.length) {
      setMessage("This desktop build could not read the dropped file paths.");
      return;
    }

    setBusy(true);
    setMessage(null);
    try {
      const response = await fetch(`${API_BASE}/input/ingest`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ paths }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || `Ingestion failed (${response.status})`);
      setAttachments((current) => [...(data as Attachment[]), ...current]);
      setMessage(`${paths.length} file${paths.length === 1 ? "" : "s"} stored locally.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "File ingestion failed.");
    } finally {
      setBusy(false);
    }
  }, []);

  const deleteAttachment = useCallback(async (token: string) => {
    try {
      const response = await fetch(`${API_BASE}/input/attachments/${encodeURIComponent(token)}`, {
        method: "DELETE",
      });
      if (!response.ok) throw new Error("Could not delete attachment");
      setAttachments((current) => current.filter((item) => item.token !== token));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not delete attachment.");
    }
  }, []);

  return (
    <section
      className={`fixed bottom-16 left-1/2 z-10 w-[min(92vw,34rem)] -translate-x-1/2 rounded-2xl border p-3 backdrop-blur transition-colors ${
        isOver
          ? "border-cyan-300/70 bg-cyan-950/70"
          : "border-cyan-200/15 bg-slate-950/65"
      }`}
      onDragEnter={(event) => {
        event.preventDefault();
        setIsOver(true);
      }}
      onDragOver={(event) => event.preventDefault()}
      onDragLeave={(event) => {
        if (event.currentTarget === event.target) setIsOver(false);
      }}
      onDrop={(event) => {
        event.preventDefault();
        setIsOver(false);
        void ingest(event.dataTransfer.files);
      }}
    >
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-[10px] uppercase tracking-[0.22em] text-cyan-100/75">Local input</p>
          <p className="mt-1 text-xs text-cyan-50/75">
            {busy ? "Validating and copying locally…" : "Drop files here or choose from this computer"}
          </p>
        </div>
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          disabled={busy}
          className="rounded-lg border border-cyan-200/20 px-3 py-2 text-[10px] uppercase tracking-[0.15em] text-cyan-100/80 hover:bg-cyan-300/10 disabled:opacity-40"
        >
          Choose
        </button>
        <input
          ref={inputRef}
          type="file"
          multiple
          className="hidden"
          onChange={(event) => {
            if (event.target.files) void ingest(event.target.files);
            event.target.value = "";
          }}
        />
      </div>
      {message && <p className="mt-2 text-[11px] text-cyan-100/65">{message}</p>}
      {attachments.length > 0 && (
        <div className="mt-3 max-h-28 space-y-1 overflow-y-auto border-t border-cyan-100/10 pt-2">
          {attachments.map((attachment) => (
            <div key={attachment.token} className="flex items-center justify-between gap-2 text-[11px] text-cyan-50/75">
              <div className="min-w-0 truncate" title={attachment.display_name}>
                <span>
                  {attachment.display_name} <span className="text-cyan-100/40">({formatBytes(attachment.size_bytes)})</span>
                </span>
                {attachment.processing_job?.status === "completed" && attachment.processing_job.summary && (
                  <p className="truncate text-cyan-100/55">Summary: {attachment.processing_job.summary}</p>
                )}
                {attachment.processing_job?.status === "queued" && (
                  <p className="text-cyan-100/45">Local summary queued…</p>
                )}
                {attachment.processing_job?.status === "running" && (
                  <p className="text-cyan-100/45">Local summary processing…</p>
                )}
                {attachment.processing_job?.status === "failed" && (
                  <p className="truncate text-red-200/65">Processing unavailable: {attachment.processing_job.error}</p>
                )}
                {!!attachment.processing_job?.memory_proposal_ids.length && (
                  <p className="text-amber-100/65">Memory proposal ready for review in Memory · M</p>
                )}
              </div>
              <button
                type="button"
                onClick={() => void deleteAttachment(attachment.token)}
                className="shrink-0 text-red-200/70 hover:text-red-100"
                aria-label={`Delete ${attachment.display_name}`}
              >
                Delete
              </button>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
