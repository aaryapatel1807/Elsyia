import { useCallback, useEffect, useRef, useState } from "react";
import { AudioQueue, VoiceRecorder, fetchSpeechUrl } from "@/lib/voice";
import type { AssistantStatus } from "@/components/Orb";

const API_BASE = "http://127.0.0.1:8000/api/v1";
const MAX_RECORDING_MS = 15000;

declare global {
  interface Window {
    elysia?: {
      version: string;
      onJevSummon?: (cb: (info?: { wake: boolean }) => void) => () => void;
      hideJevOverlay?: () => void;
      setWakeWordPolling?: (enabled: boolean) => void;
    };
  }
}

interface JevAction {
  tool: string;
  status: string;
  confirmation_required: boolean;
  confirmation_message?: string | null;
  error?: string | null;
}

interface JevTurn {
  transcript: string;
  reply: string;
  conversation_id: string;
  intent: string;
  actions: JevAction[];
  timings_ms: Record<string, number>;
}

const ACTION_LABELS: Record<string, string> = {
  play_youtube: "YouTube",
  media_control: "Media",
  message_whatsapp: "WhatsApp",
  open_linkedin: "LinkedIn",
  open_spotify: "Spotify",
  check_gmail: "Gmail",
  search_gmail: "Gmail",
  send_gmail: "Gmail",
  calendar_today: "Calendar",
  create_calendar_event: "Calendar",
  set_timer: "Timer",
  take_note: "Note",
  get_current_time: "Clock",
};

function splitSentences(text: string): string[] {
  return text
    .split(/(?<=[.!?])\s+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

/**
 * Jev's summon overlay: the always-available voice interface.
 * Toggled from anywhere with Ctrl+Shift+J. One tight loop —
 * hold to talk, release, Jev thinks and speaks back.
 */
export default function JevOverlay() {
  const [status, setStatus] = useState<AssistantStatus>("idle");
  const [transcript, setTranscript] = useState("");
  const [reply, setReply] = useState("");
  const [actions, setActions] = useState<JevAction[]>([]);
  const [timings, setTimings] = useState<Record<string, number>>({});
  const [error, setError] = useState<string | null>(null);
  const [pendingConfirm, setPendingConfirm] = useState<JevAction | null>(null);
  const [wakeOn, setWakeOn] = useState(false);
  const [wakeModel, setWakeModel] = useState("hey jarvis");
  const [wakeAvailable, setWakeAvailable] = useState(true);
  const wakeTurnRef = useRef(false);

  const recorderRef = useRef<VoiceRecorder | null>(null);
  const audioQueueRef = useRef<AudioQueue | null>(null);
  const conversationIdRef = useRef<string | undefined>(undefined);
  const autoStopRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastTranscriptRef = useRef("");

  const stopAll = useCallback(() => {
    audioQueueRef.current?.stop();
    audioQueueRef.current = null;
    setStatus("idle");
  }, []);

  /** Soft two-tone chime played when the wake word summons Jev. */
  const playWakeChime = useCallback(() => {
    try {
      const Ctx =
        window.AudioContext ??
        (window as unknown as { webkitAudioContext: typeof AudioContext })
          .webkitAudioContext;
      const ctx = new Ctx();
      const now = ctx.currentTime;
      [880, 1318.5].forEach((freq, i) => {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = "sine";
        osc.frequency.value = freq;
        const t0 = now + i * 0.13;
        gain.gain.setValueAtTime(0.0001, t0);
        gain.gain.exponentialRampToValueAtTime(0.22, t0 + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.3);
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start(t0);
        osc.stop(t0 + 0.34);
      });
      window.setTimeout(() => void ctx.close(), 700);
    } catch {
      // Audio unavailable — the summon still works, just silently.
    }
  }, []);

  /** A wake-initiated turn finished: the listener goes back to sleep-watch. */
  const endWakeTurn = useCallback(() => {
    if (!wakeTurnRef.current) return;
    wakeTurnRef.current = false;
    fetch(`${API_BASE}/jev/wakeword/resume`, { method: "POST" }).catch(() => {});
  }, []);

  const speakReply = useCallback(
    (text: string) => {
      const sentences = splitSentences(text);
      if (sentences.length === 0) {
        endWakeTurn();
        setStatus("idle");
        return;
      }
      setStatus("speaking");
      const queue = new AudioQueue();
      queue.onComplete = () => {
        endWakeTurn();
        setStatus("idle");
      };
      audioQueueRef.current = queue;
      // Fire all TTS requests at once; the queue plays them in order,
      // so the first sentence starts speaking ASAP (perceived latency win).
      sentences.forEach((sentence) => {
        fetchSpeechUrl(sentence)
          .then((url) => queue.enqueue(url))
          .catch((err) => console.error("TTS failed for chunk:", err));
      });
    },
    [endWakeTurn]
  );

  const runTurn = useCallback(
    async (audioBlob: Blob, confirmed: string[]) => {
      try {
        setStatus("thinking");
        const form = new FormData();
        form.append("audio", audioBlob, "turn.webm");
        if (conversationIdRef.current) form.append("conversation_id", conversationIdRef.current);
        if (confirmed.length > 0) form.append("confirmed", confirmed.join(","));

        const res = await fetch(`${API_BASE}/jev/turn`, { method: "POST", body: form });
        if (!res.ok) throw new Error(`Jev turn failed: ${res.status}`);
        const turn = (await res.json()) as JevTurn;

        conversationIdRef.current = turn.conversation_id;
        setTranscript(turn.transcript);
        lastTranscriptRef.current = turn.transcript;
        setReply(turn.reply);
        setActions(turn.actions);
        setTimings(turn.timings_ms);

        const needsConfirm = turn.actions.find((a) => a.confirmation_required);
        setPendingConfirm(needsConfirm ?? null);
        if (!turn.transcript.trim()) {
          setError("Didn't catch that — hold a little longer");
          endWakeTurn();
          setStatus("idle");
          return;
        }
        speakReply(turn.reply);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Voice loop failed.");
        endWakeTurn();
        setStatus("idle");
      }
    },
    [speakReply, endWakeTurn]
  );

  const stopListeningAndRespond = useCallback(async () => {
    const recorder = recorderRef.current;
    if (!recorder) return;
    recorderRef.current = null;
    if (autoStopRef.current) {
      clearTimeout(autoStopRef.current);
      autoStopRef.current = null;
    }
    try {
      const audioBlob = await recorder.stop();
      await runTurn(audioBlob, []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Microphone failed.");
      endWakeTurn();
      setStatus("idle");
    }
  }, [runTurn, endWakeTurn]);

  const startListening = useCallback(async () => {
    if (recorderRef.current) return;
    stopAll();
    setError(null);
    setPendingConfirm(null);
    try {
      const recorder = new VoiceRecorder();
      await recorder.start();
      recorderRef.current = recorder;
      setStatus("listening");
      autoStopRef.current = setTimeout(() => void stopListeningAndRespond(), MAX_RECORDING_MS);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Microphone access failed.");
      setStatus("idle");
    }
  }, [stopAll, stopListeningAndRespond]);

  const confirmAction = useCallback(async () => {
    if (!pendingConfirm || !lastTranscriptRef.current) return;
    setPendingConfirm(null);
    setStatus("thinking");
    try {
      // Re-run the same command with the tool confirmed. We re-send the
      // last transcript as a text turn to avoid re-recording audio.
      const res = await fetch(`${API_BASE}/jev/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: lastTranscriptRef.current,
          conversation_id: conversationIdRef.current,
          confirmed: [pendingConfirm.tool],
        }),
      });
      if (!res.ok) throw new Error(`Confirm failed: ${res.status}`);
      const turn = (await res.json()) as JevTurn;
      setReply(turn.reply);
      setActions(turn.actions);
      setTimings(turn.timings_ms);
      setPendingConfirm(turn.actions.find((a) => a.confirmation_required) ?? null);
      speakReply(turn.reply);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Confirm failed.");
      setStatus("idle");
    }
  }, [pendingConfirm, speakReply]);

  // Global hotkey summons us from the main process; Space is PTT inside.
  // A wake-word summon arrives with { wake: true }: chime, then listen hands-free.
  useEffect(() => {
    const off = window.elysia?.onJevSummon?.((info) => {
      if (info?.wake) {
        wakeTurnRef.current = true;
        playWakeChime();
      }
      void startListening();
    });
    const onKey = (e: KeyboardEvent) => {
      if (e.code === "Space") {
        e.preventDefault();
        if (!e.repeat && status === "idle") void startListening();
        if (!e.repeat && status === "listening") void stopListeningAndRespond();
      }
      if (e.code === "Escape") {
        e.preventDefault();
        if (status === "listening") void stopListeningAndRespond();
        else {
          stopAll();
          window.elysia?.hideJevOverlay?.();
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      off?.();
      window.removeEventListener("keydown", onKey);
    };
  }, [startListening, stopListeningAndRespond, stopAll, status, playWakeChime]);

  // Wake-word toggle: explicit opt-in for the always-on listener.
  useEffect(() => {
    fetch(`${API_BASE}/jev/wakeword/status`)
      .then((r) => (r.ok ? r.json() : null))
      .then((s: { enabled?: boolean; model?: string; available?: boolean } | null) => {
        if (!s) return;
        setWakeOn(!!s.enabled);
        if (s.model) setWakeModel(String(s.model).replace(/_/g, " "));
        setWakeAvailable(s.available !== false);
        window.elysia?.setWakeWordPolling?.(!!s.enabled);
      })
      .catch(() => {});
  }, []);

  const toggleWakeWord = useCallback(async () => {
    const next = !wakeOn;
    try {
      const res = await fetch(
        `${API_BASE}/jev/wakeword/${next ? "enable" : "disable"}`,
        { method: "POST" }
      );
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setError(
          typeof body.detail === "string"
            ? body.detail
            : "Wake-word listener unavailable on this machine."
        );
        return;
      }
      const s = (await res.json()) as {
        enabled?: boolean;
        model?: string;
        available?: boolean;
      };
      setWakeOn(!!s.enabled);
      if (s.model) setWakeModel(String(s.model).replace(/_/g, " "));
      setWakeAvailable(s.available !== false);
      window.elysia?.setWakeWordPolling?.(!!s.enabled);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Wake-word toggle failed.");
    }
  }, [wakeOn]);

  const totalMs = timings.total_ms;
  const orbClass =
    status === "listening"
      ? "jev-orb-listening"
      : status === "thinking"
        ? "jev-orb-thinking"
        : status === "speaking"
          ? "jev-orb-speaking"
          : "jev-orb-idle";

  return (
    <div className="jev-overlay">
      <style>{`
        .jev-overlay {
          width: 100vw; height: 100vh; display: flex; flex-direction: column;
          align-items: center; justify-content: flex-start;
          background: rgba(8, 8, 14, 0.82); backdrop-filter: blur(28px);
          border-radius: 24px; border: 1px solid rgba(255,255,255,0.09);
          color: #f2f2f5; font-family: ui-sans-serif, system-ui, sans-serif;
          padding: 28px 24px; box-sizing: border-box; overflow: hidden;
          -webkit-app-region: drag;
        }
        .jev-overlay button { -webkit-app-region: no-drag; }
        .jev-title { font-size: 13px; letter-spacing: 0.32em; color: #9a9ab0; margin-bottom: 18px; }
        .jev-orb { width: 128px; height: 128px; border-radius: 50%; margin: 6px 0 18px;
          transition: box-shadow 0.4s ease, transform 0.4s ease; }
        .jev-orb-idle { background: radial-gradient(circle at 35% 35%, #3b3b58, #15151f);
          box-shadow: 0 0 42px rgba(120,120,200,0.25); }
        .jev-orb-listening { background: radial-gradient(circle at 35% 35%, #4f7cff, #1b2a6b);
          box-shadow: 0 0 64px rgba(90,140,255,0.65); transform: scale(1.06);
          animation: jev-pulse 1.4s ease-in-out infinite; }
        .jev-orb-thinking { background: radial-gradient(circle at 35% 35%, #a06bff, #3a1f6e);
          box-shadow: 0 0 64px rgba(160,110,255,0.6); animation: jev-spin 2.4s linear infinite; }
        .jev-orb-speaking { background: radial-gradient(circle at 35% 35%, #37e0a0, #0e5c3d);
          box-shadow: 0 0 64px rgba(60,224,160,0.55); animation: jev-pulse 0.9s ease-in-out infinite; }
        @keyframes jev-pulse { 0%,100% { transform: scale(1.04);} 50% { transform: scale(1.12);} }
        @keyframes jev-spin { from { filter: hue-rotate(0deg);} to { filter: hue-rotate(360deg);} }
        .jev-status { font-size: 12px; letter-spacing: 0.22em; color: #8b8ba3; text-transform: uppercase; min-height: 18px; }
        .jev-text { width: 100%; margin-top: 14px; max-height: 220px; overflow-y: auto; }
        .jev-transcript { font-size: 13px; color: #9a9ab0; font-style: italic; margin-bottom: 8px; }
        .jev-reply { font-size: 16px; line-height: 1.55; color: #f2f2f5; }
        .jev-chips { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
        .jev-chip { font-size: 11px; letter-spacing: 0.08em; padding: 5px 12px; border-radius: 999px;
          background: rgba(120,140,255,0.14); border: 1px solid rgba(120,140,255,0.35); color: #b9c6ff; }
        .jev-timing { margin-top: 10px; font-size: 11px; color: #6d6d85; letter-spacing: 0.06em; }
        .jev-error { margin-top: 10px; font-size: 13px; color: #ff9d9d; }
        .jev-ptt { margin-top: auto; width: 100%; padding: 14px; border-radius: 16px; border: none;
          font-size: 15px; font-weight: 600; letter-spacing: 0.04em; cursor: pointer;
          background: linear-gradient(135deg, #4f7cff, #8a5cff); color: white; }
        .jev-ptt:active { transform: scale(0.98); }
        .jev-confirm { display: flex; gap: 10px; width: 100%; margin-top: 12px; }
        .jev-confirm button { flex: 1; padding: 12px; border-radius: 14px; border: none;
          font-size: 14px; font-weight: 600; cursor: pointer; }
        .jev-confirm-yes { background: #2fbf71; color: #06130c; }
        .jev-confirm-no { background: rgba(255,255,255,0.1); color: #f2f2f5; }
        .jev-hint { margin-top: 10px; font-size: 11px; color: #6d6d85; }
        .jev-wake { width: 100%; margin-top: 12px; padding: 10px 12px; border-radius: 12px;
          background: rgba(120,140,255,0.07); border: 1px solid rgba(120,140,255,0.18);
          box-sizing: border-box; -webkit-app-region: no-drag; }
        .jev-wake-label { display: flex; align-items: center; gap: 10px; font-size: 12px;
          color: #b9c6ff; cursor: pointer; letter-spacing: 0.04em; }
        .jev-wake-warn { margin-top: 6px; font-size: 11px; color: #ff9d9d; }
      `}</style>

      <div className="jev-title">JEV</div>
      <div className={`jev-orb ${orbClass}`} />
      <div className="jev-status">
        {status === "idle" && "hold space to talk"}
        {status === "listening" && "listening…"}
        {status === "thinking" && "thinking…"}
        {status === "speaking" && "speaking…"}
      </div>

      <div className="jev-text">
        {transcript && <div className="jev-transcript">“{transcript}”</div>}
        {reply && <div className="jev-reply">{reply}</div>}
        {actions.length > 0 && (
          <div className="jev-chips">
            {actions.map((a, i) => (
              <span key={i} className="jev-chip">
                {ACTION_LABELS[a.tool] ?? a.tool}
                {a.status === "error" ? " · failed" : ""}
                {a.confirmation_required ? " · confirm?" : ""}
              </span>
            ))}
          </div>
        )}
        {typeof totalMs === "number" && (
          <div className="jev-timing">answered in {(totalMs / 1000).toFixed(1)}s</div>
        )}
        {error && <div className="jev-error">{error}</div>}
      </div>

      {pendingConfirm ? (
        <div className="jev-confirm">
          <button className="jev-confirm-yes" onClick={() => void confirmAction()}>
            Yes, do it
          </button>
          <button
            className="jev-confirm-no"
            onClick={() => {
              setPendingConfirm(null);
              setReply("Understood — I won't do that.");
              speakReply("Understood — I won't do that.");
            }}
          >
            No
          </button>
        </div>
      ) : (
        <button
          className="jev-ptt"
          onMouseDown={() => void startListening()}
          onMouseUp={() => void stopListeningAndRespond()}
          onMouseLeave={() => {
            if (status === "listening") void stopListeningAndRespond();
          }}
        >
          {status === "listening" ? "Release to send" : "Hold to talk to Jev"}
        </button>
      )}
      <div className="jev-wake">
        <label className="jev-wake-label">
          <input
            type="checkbox"
            checked={wakeOn}
            onChange={() => void toggleWakeWord()}
            aria-label="Wake word listener"
          />
          <span>Wake word · “{wakeModel}”</span>
        </label>
        {!wakeAvailable && (
          <div className="jev-wake-warn">listener unavailable on this machine</div>
        )}
      </div>
      <div className="jev-hint">Ctrl+Shift+J anywhere to summon · Esc to dismiss</div>
    </div>
  );
}
