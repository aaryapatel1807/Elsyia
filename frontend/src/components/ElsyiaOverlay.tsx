import { useCallback, useEffect, useRef, useState } from "react";
import { AudioQueue, VoiceRecorder, fetchSpeechUrl, transcribe } from "@/lib/voice";
import type { AssistantStatus } from "@/components/Orb";
import { apiBase } from "../lib/api";

const API_BASE = apiBase();
const MAX_RECORDING_MS = 15000;
/** Dictation can run longer than an assistant turn — two minutes of speech. */
const MAX_DICTATION_MS = 120000;

declare global {
  interface Window {
    elysia?: {
      version: string;
      onElsyiaSummon?: (cb: (info?: { wake: boolean; dictate?: boolean; see?: boolean; thumbnail?: string }) => void) => () => void;
      hideElsyiaOverlay?: () => void;
      setWakeWordPolling?: (enabled: boolean) => void;
      /** Fired when the wake-word switch changes elsewhere (e.g. tray menu). */
      onWakeWordState?: (cb: (on: boolean) => void) => () => void;
      /** [elsyia-see] Region-select overlay: report the user-dragged
       * rectangle (CSS px). This is the only path that leads to a
       * screen capture. */
      selectSeeRegion?: (rect: {
        x: number;
        y: number;
        width: number;
        height: number;
      }) => void;
      /** [elsyia-see] Cancel the region select — no capture happens. */
      cancelSeeSelect?: () => void;
    };
  }
}

interface ElsyiaAction {
  tool: string;
  status: string;
  confirmation_required: boolean;
  confirmation_message?: string | null;
  error?: string | null;
}

interface ElsyiaTurn {
  transcript: string;
  reply: string;
  conversation_id: string;
  intent: string;
  actions: ElsyiaAction[];
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

/** One agent-mode step as the backend reports it. */
interface AgentStepState {
  seq: number;
  tool: string;
  say: string;
  status: string;
  confirmation_message?: string | null;
  error?: string | null;
}

function toAgentStepState(s: any): AgentStepState {
  return {
    seq: s.seq,
    tool: s.tool,
    say: s.say,
    status: s.status,
    confirmation_message: s.confirmation_message ?? null,
    error: s.error ?? null,
  };
}

/** Read a POST SSE stream (EventSource can't POST), dispatching each event. */
async function readAgentStream(
  res: Response,
  onEvent: (e: any) => void
): Promise<void> {
  const reader = res.body?.getReader();
  if (!reader) throw new Error("Streaming not supported in this browser.");
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const chunks = buf.split("\n\n");
    buf = chunks.pop() ?? "";
    for (const chunk of chunks) {
      const line = chunk.split("\n").find((l) => l.startsWith("data:"));
      if (!line) continue;
      try {
        onEvent(JSON.parse(line.slice(5).trim()));
      } catch {
        /* keep the stream alive on a malformed event */
      }
    }
  }
}

/**
 * Elsyia's summon overlay: the always-available voice interface.
 * Toggled from anywhere with Ctrl+Shift+J. One tight loop —
 * hold to talk, release, Elsyia thinks and speaks back.
 */
export default function ElsyiaOverlay() {
  const [status, setStatus] = useState<AssistantStatus>("idle");
  const [transcript, setTranscript] = useState("");
  const [reply, setReply] = useState("");
  const [actions, setActions] = useState<ElsyiaAction[]>([]);
  const [timings, setTimings] = useState<Record<string, number>>({});
  const [error, setError] = useState<string | null>(null);
  const [pendingConfirm, setPendingConfirm] = useState<ElsyiaAction | null>(null);
  const [wakeOn, setWakeOn] = useState(false);
  const [wakeModel, setWakeModel] = useState("hey jarvis");
  const [wakeAvailable, setWakeAvailable] = useState(true);
  const wakeTurnRef = useRef(false);

  const recorderRef = useRef<VoiceRecorder | null>(null);
  const audioQueueRef = useRef<AudioQueue | null>(null);
  const conversationIdRef = useRef<string | undefined>(undefined);
  const autoStopRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastTranscriptRef = useRef("");

  // --- Dictation mode (say it, it types): a separate, silent mode. ---
  const [dictateMode, setDictateMode] = useState(false);
  const [dictateText, setDictateText] = useState("");
  const [dictateBusy, setDictateBusy] = useState(false);
  const [dictateConfirm, setDictateConfirm] = useState(true);
  const [dictateAvailable, setDictateAvailable] = useState(true);
  const [dictateRecording, setDictateRecording] = useState(false);
  const dictateRecorderRef = useRef<VoiceRecorder | null>(null);
  const dictateAutoStopRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const dictateConfirmRef = useRef(true);

  // --- Agent mode ("say it and it's done" multi-step chaining). ---
  const [agentMode, setAgentMode] = useState(false);
  const [agentInput, setAgentInput] = useState("");
  const [agentSteps, setAgentSteps] = useState<AgentStepState[]>([]);
  const [agentBusy, setAgentBusy] = useState(false);
  const [agentPending, setAgentPending] = useState<{
    planId: string;
    tool: string;
    message: string;
  } | null>(null);

  // --- Screen-aware mode ("circle anything, then just ask"). ---
  // Entered only via the explicit region-select hotkey (Ctrl+Shift+S);
  // the overlay never captures on its own.
  const [seeMode, setSeeMode] = useState(false);
  const [seeThumb, setSeeThumb] = useState<string | null>(null);
  const [seeQuestion, setSeeQuestion] = useState("");
  const [seeAnswer, setSeeAnswer] = useState("");
  const [seeOk, setSeeOk] = useState(true);
  const [seeBusy, setSeeBusy] = useState(false);
  const [seeMs, setSeeMs] = useState<number | null>(null);
  const [seeVoiceAsking, setSeeVoiceAsking] = useState(false);
  const seeRecorderRef = useRef<VoiceRecorder | null>(null);

  const stopAll = useCallback(() => {
    audioQueueRef.current?.stop();
    audioQueueRef.current = null;
    setStatus("idle");
  }, []);

  /** Soft two-tone chime played when the wake word summons Elsyia. */
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
    fetch(`${API_BASE}/elsyia/wakeword/resume`, { method: "POST" }).catch(() => {});
  }, []);

  /** --- Dictation mode: say it, it types. Silent — Elsyia never speaks here. --- */

  const pauseWakeForDictation = useCallback(() => {
    fetch(`${API_BASE}/elsyia/wakeword/pause`, { method: "POST" }).catch(() => {});
  }, []);

  const resumeWakeAfterDictation = useCallback(() => {
    fetch(`${API_BASE}/elsyia/wakeword/resume`, { method: "POST" }).catch(() => {});
  }, []);

  const resetDictation = useCallback(() => {
    dictateRecorderRef.current = null;
    if (dictateAutoStopRef.current) {
      clearTimeout(dictateAutoStopRef.current);
      dictateAutoStopRef.current = null;
    }
    setDictateMode(false);
    setDictateRecording(false);
    setDictateText("");
    setDictateBusy(false);
    setStatus("idle");
  }, []);

  const cancelDictation = useCallback(() => {
    // Discard the recording — nothing is sent, nothing is typed.
    const rec = dictateRecorderRef.current;
    dictateRecorderRef.current = null;
    if (rec) void rec.stop().catch(() => {});
    resetDictation();
    resumeWakeAfterDictation();
    window.elysia?.hideElsyiaOverlay?.();
  }, [resetDictation, resumeWakeAfterDictation]);

  const typeDictation = useCallback(
    async (text: string) => {
      const clean = text.trim();
      if (!clean) {
        cancelDictation();
        return;
      }
      setDictateBusy(true);
      try {
        // Hide FIRST so OS focus returns to the target app, then type into it.
        window.elysia?.hideElsyiaOverlay?.();
        await new Promise((r) => setTimeout(r, 250));
        const res = await fetch(`${API_BASE}/elsyia/dictate/type`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: clean }),
        });
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(
            typeof body.detail === "string" ? body.detail : `Type failed: ${res.status}`
          );
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Typing failed.");
      } finally {
        setDictateBusy(false);
        resetDictation();
        resumeWakeAfterDictation();
      }
    },
    [cancelDictation, resetDictation, resumeWakeAfterDictation]
  );

  const finishDictation = useCallback(async () => {
    const recorder = dictateRecorderRef.current;
    if (!recorder) return;
    dictateRecorderRef.current = null;
    setDictateRecording(false);
    if (dictateAutoStopRef.current) {
      clearTimeout(dictateAutoStopRef.current);
      dictateAutoStopRef.current = null;
    }
    setDictateBusy(true);
    setStatus("thinking");
    try {
      const audioBlob = await recorder.stop();
      const form = new FormData();
      form.append("audio", audioBlob, "dictate.webm");
      const res = await fetch(`${API_BASE}/elsyia/dictate`, { method: "POST", body: form });
      if (!res.ok) throw new Error(`Dictation failed: ${res.status}`);
      const data = (await res.json()) as { transcript?: string; cleaned?: string };
      const cleaned = (data.cleaned ?? "").trim();
      if (!cleaned) {
        setError("Didn't catch that — press the hotkey to try again");
        resetDictation();
        resumeWakeAfterDictation();
        return;
      }
      setDictateText(cleaned);
      if (!dictateConfirmRef.current) {
        await typeDictation(cleaned);
      }
      // Otherwise stay in dictateMode showing the preview; hotkey confirms.
    } catch (err) {
      setError(err instanceof Error ? err.message : "Dictation failed.");
      resetDictation();
      resumeWakeAfterDictation();
    } finally {
      setDictateBusy(false);
    }
  }, [typeDictation, resetDictation, resumeWakeAfterDictation]);

  const startDictation = useCallback(async () => {
    if (dictateRecorderRef.current) return;
    stopAll();
    setError(null);
    setDictateText("");
    pauseWakeForDictation();
    try {
      const recorder = new VoiceRecorder();
      await recorder.start();
      dictateRecorderRef.current = recorder;
      setDictateMode(true);
      setDictateRecording(true);
      setStatus("listening");
      dictateAutoStopRef.current = setTimeout(() => {
        void finishDictation();
      }, MAX_DICTATION_MS);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Microphone access failed.");
      resetDictation();
      resumeWakeAfterDictation();
    }
  }, [stopAll, pauseWakeForDictation, resetDictation, resumeWakeAfterDictation, finishDictation]);

  const toggleDictation = useCallback(() => {
    if (dictateRecorderRef.current) {
      void finishDictation(); // recording -> stop & process
    } else if (dictateMode && dictateText && !dictateBusy) {
      void typeDictation(dictateText); // preview -> hotkey means "type it"
    } else if (!dictateMode) {
      void startDictation();
    }
  }, [dictateMode, dictateText, dictateBusy, finishDictation, typeDictation, startDictation]);

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

  // --- Screen-aware mode ("circle anything, then just ask"). ---
  // Entered ONLY via the explicit region-select hotkey; the overlay
  // never captures on its own.

  /** Enter see-mode after an explicit region capture. */
  const enterSeeMode = useCallback(
    (thumbnail?: string) => {
      stopAll();
      setError(null);
      setSeeMode(true);
      setSeeThumb(thumbnail ?? null);
      setSeeQuestion("");
      setSeeAnswer("");
      setSeeOk(true);
      setSeeMs(null);
    },
    [stopAll]
  );

  const exitSeeMode = useCallback(() => {
    seeRecorderRef.current = null;
    setSeeVoiceAsking(false);
    setSeeMode(false);
    setSeeThumb(null);
    setSeeQuestion("");
    setSeeAnswer("");
  }, []);

  /** Ask a question about the current explicit capture. */
  const askSee = useCallback(
    async (question: string) => {
      const q = question.trim();
      if (!q || seeBusy) return;
      setSeeBusy(true);
      setError(null);
      setSeeAnswer("");
      setStatus("thinking");
      try {
        const res = await fetch(`${API_BASE}/elsyia/see`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ question: q }),
        });
        if (!res.ok) throw new Error(`See failed: ${res.status}`);
        const data = (await res.json()) as {
          ok: boolean;
          answer: string;
          timings_ms?: { total_ms?: number };
        };
        setSeeOk(!!data.ok);
        setSeeAnswer(data.answer);
        setSeeMs(data.timings_ms?.total_ms ?? null);
        speakReply(data.answer);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Screen-aware failed.");
        setStatus("idle");
      } finally {
        setSeeBusy(false);
      }
    },
    [seeBusy, speakReply]
  );

  /** Ask by voice: record, transcribe, then ask about the capture. */
  const askSeeByVoice = useCallback(async () => {
    const active = seeRecorderRef.current;
    if (active) {
      seeRecorderRef.current = null;
      setSeeVoiceAsking(false);
      try {
        const audio = await active.stop();
        const text = await transcribe(audio);
        if (text.trim()) {
          setSeeQuestion(text.trim());
          await askSee(text.trim());
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Microphone failed.");
      }
      return;
    }
    try {
      const recorder = new VoiceRecorder();
      await recorder.start();
      seeRecorderRef.current = recorder;
      setSeeVoiceAsking(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Microphone access failed.");
    }
  }, [askSee]);

  const runTurn = useCallback(
    async (audioBlob: Blob, confirmed: string[]) => {
      try {
        setStatus("thinking");
        const form = new FormData();
        form.append("audio", audioBlob, "turn.webm");
        if (conversationIdRef.current) form.append("conversation_id", conversationIdRef.current);
        if (confirmed.length > 0) form.append("confirmed", confirmed.join(","));

        const res = await fetch(`${API_BASE}/elsyia/turn`, { method: "POST", body: form });
        if (!res.ok) throw new Error(`Elsyia turn failed: ${res.status}`);
        const turn = (await res.json()) as ElsyiaTurn;

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
      const res = await fetch(`${API_BASE}/elsyia/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: lastTranscriptRef.current,
          conversation_id: conversationIdRef.current,
          confirmed: [pendingConfirm.tool],
        }),
      });
      if (!res.ok) throw new Error(`Confirm failed: ${res.status}`);
      const turn = (await res.json()) as ElsyiaTurn;
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

  const applyAgentStep = useCallback((incoming: AgentStepState) => {
    setAgentSteps((prev) => {
      const idx = prev.findIndex((s) => s.seq === incoming.seq);
      if (idx === -1) return [...prev, incoming].sort((a, b) => a.seq - b.seq);
      const next = [...prev];
      next[idx] = incoming;
      return next;
    });
  }, []);

  const handleAgentEvent = useCallback(
    (e: any) => {
      switch (e.type) {
        case "plan_created":
          setAgentSteps(((e.plan?.steps ?? []) as any[]).map(toAgentStepState));
          break;
        case "step_started":
          applyAgentStep({
            seq: e.seq,
            tool: e.tool,
            say: e.say,
            status: "running",
          });
          break;
        case "step_completed":
        case "step_failed":
        case "step_awaiting_confirmation":
          applyAgentStep(toAgentStepState(e.step));
          break;
        case "awaiting_confirmation": {
          const steps = ((e.plan?.steps ?? []) as any[]).map(toAgentStepState);
          setAgentSteps(steps);
          const pending = steps.find((s) => s.status === "awaiting_confirmation");
          if (pending) {
            setAgentPending({
              planId: e.plan.plan_id,
              tool: pending.tool,
              message:
                pending.confirmation_message ?? "This step needs your approval.",
            });
          }
          break;
        }
        case "plan_completed":
        case "plan_failed":
          setAgentSteps(((e.plan?.steps ?? []) as any[]).map(toAgentStepState));
          setReply(e.reply ?? "");
          speakReply(e.reply ?? "Done.");
          setAgentPending(null);
          break;
        case "no_plan":
          setReply(e.reply ?? "");
          speakReply(e.reply ?? "Done.");
          break;
        default:
          break;
      }
    },
    [applyAgentStep, speakReply]
  );

  const runAgent = useCallback(async (override?: string) => {
    const message = (override ?? agentInput).trim();
    if (!message || agentBusy) return;
    stopAll();
    setError(null);
    setReply("");
    setTranscript("");
    setActions([]);
    setAgentSteps([]);
    setAgentPending(null);
    setAgentBusy(true);
    setStatus("thinking");
    try {
      const res = await fetch(`${API_BASE}/elsyia/agent`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, stream: true }),
      });
      if (!res.ok) throw new Error(`Agent run failed: ${res.status}`);
      await readAgentStream(res, handleAgentEvent);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Agent run failed.");
    } finally {
      setAgentBusy(false);
      setStatus("idle");
    }
  }, [agentInput, agentBusy, stopAll, handleAgentEvent]);

  /** [elsyia-see] Hand the see-mode question to agent mode: the planner can
   * chain see_capture into real tools (e.g. send_gmail) with its
   * normal confirm gates. */
  const doItWithAgent = useCallback(() => {
    const q = seeQuestion.trim();
    if (!q) return;
    setSeeMode(false);
    setAgentMode(true);
    void runAgent(q);
  }, [seeQuestion, runAgent]);

  const confirmAgentRun = useCallback(async () => {
    if (!agentPending) return;
    const { planId, tool } = agentPending;
    setAgentPending(null);
    setStatus("thinking");
    try {
      const res = await fetch(`${API_BASE}/elsyia/agent/${planId}/confirm`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirmed: [tool], stream: true }),
      });
      if (!res.ok) throw new Error(`Confirm failed: ${res.status}`);
      await readAgentStream(res, handleAgentEvent);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Confirm failed.");
    } finally {
      setStatus("idle");
    }
  }, [agentPending, handleAgentEvent]);

  const denyAgentRun = useCallback(async () => {
    if (!agentPending) return;
    try {
      await fetch(`${API_BASE}/elsyia/agent/${agentPending.planId}/cancel`, {
        method: "POST",
      });
    } catch {
      /* best effort — the plan simply stays paused and expires */
    }
    setAgentPending(null);
    setReply("Understood — I won't do that.");
    speakReply("Understood — I won't do that.");
  }, [agentPending, speakReply]);

  // Global hotkey summons us from the main process; Space is PTT inside.
  // A wake-word summon arrives with { wake: true }: chime, then listen hands-free.
  // A dictation summon arrives with { dictate: true }: toggle record/stop/type.
  useEffect(() => {
    const off = window.elysia?.onElsyiaSummon?.((info) => {
      if (info?.dictate) {
        toggleDictation();
        return;
      }
      if (info?.see) {
        enterSeeMode(info.thumbnail);
        return;
      }
      if (info?.wake) {
        wakeTurnRef.current = true;
        playWakeChime();
      }
      void startListening();
    });
    const onKey = (e: KeyboardEvent) => {
      if (e.code === "Space" && seeMode && !dictateMode) {
        // In see-mode, Space asks about the capture by voice.
        e.preventDefault();
        if (!e.repeat) void askSeeByVoice();
      } else if (e.code === "Space" && !dictateMode) {
        e.preventDefault();
        if (!e.repeat && status === "idle") void startListening();
        if (!e.repeat && status === "listening") void stopListeningAndRespond();
      }
      if (e.code === "Escape") {
        e.preventDefault();
        // Esc in see-mode just leaves see-mode; the capture itself
        // expires from memory on its own TTL.
        if (seeMode) {
          exitSeeMode();
          return;
        }
        // Esc mid-dictation always cancels the whole dictation turn.
        if (dictateMode) {
          cancelDictation();
          return;
        }
        if (status === "listening") void stopListeningAndRespond();
        else {
          stopAll();
          window.elysia?.hideElsyiaOverlay?.();
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      off?.();
      window.removeEventListener("keydown", onKey);
    };
  }, [
    startListening,
    stopListeningAndRespond,
    stopAll,
    status,
    playWakeChime,
    dictateMode,
    toggleDictation,
    cancelDictation,
    seeMode,
    enterSeeMode,
    exitSeeMode,
    askSeeByVoice,
  ]);

  // Wake-word toggle: explicit opt-in for the always-on listener.
  useEffect(() => {
    fetch(`${API_BASE}/elsyia/wakeword/status`)
      .then((r) => (r.ok ? r.json() : null))
      .then((s: { enabled?: boolean; model?: string; available?: boolean } | null) => {
        if (!s) return;
        setWakeOn(!!s.enabled);
        if (s.model) setWakeModel(String(s.model).replace(/_/g, " "));
        setWakeAvailable(s.available !== false);
        window.elysia?.setWakeWordPolling?.(!!s.enabled);
      })
      .catch(() => {});
    // Stay in sync when the switch is flipped from the tray menu.
    const off = window.elysia?.onWakeWordState?.((on: boolean) => setWakeOn(on));
    return () => off?.();
  }, []);

  // Dictation capability: confirm-preview setting + whether typing works here.
  useEffect(() => {
    fetch(`${API_BASE}/elsyia/dictation/status`)
      .then((r) => (r.ok ? r.json() : null))
      .then(
        (s: { confirm?: boolean; typing_available?: boolean } | null) => {
          if (!s) return;
          const confirm = s.confirm !== false;
          setDictateConfirm(confirm);
          dictateConfirmRef.current = confirm;
          setDictateAvailable(s.typing_available !== false);
        }
      )
      .catch(() => {});
  }, []);

  const toggleWakeWord = useCallback(async () => {
    const next = !wakeOn;
    try {
      const res = await fetch(
        `${API_BASE}/elsyia/wakeword/${next ? "enable" : "disable"}`,
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
      ? "elsyia-orb-listening"
      : status === "thinking"
        ? "elsyia-orb-thinking"
        : status === "speaking"
          ? "elsyia-orb-speaking"
          : "elsyia-orb-idle";

  return (
    <div className="elsyia-overlay">
      <style>{`
        .elsyia-overlay {
          width: 100vw; height: 100vh; display: flex; flex-direction: column;
          align-items: center; justify-content: flex-start;
          background: rgba(8, 8, 14, 0.82); backdrop-filter: blur(28px);
          border-radius: 24px; border: 1px solid rgba(255,255,255,0.09);
          color: #f2f2f5; font-family: ui-sans-serif, system-ui, sans-serif;
          padding: 28px 24px; box-sizing: border-box; overflow: hidden;
          -webkit-app-region: drag;
        }
        .elsyia-overlay button { -webkit-app-region: no-drag; }
        .elsyia-title { font-size: 13px; letter-spacing: 0.32em; color: #9a9ab0; margin-bottom: 18px; }
        .elsyia-orb { width: 128px; height: 128px; border-radius: 50%; margin: 6px 0 18px;
          transition: box-shadow 0.4s ease, transform 0.4s ease; }
        .elsyia-orb-idle { background: radial-gradient(circle at 35% 35%, #3b3b58, #15151f);
          box-shadow: 0 0 42px rgba(120,120,200,0.25); }
        .elsyia-orb-listening { background: radial-gradient(circle at 35% 35%, #4f7cff, #1b2a6b);
          box-shadow: 0 0 64px rgba(90,140,255,0.65); transform: scale(1.06);
          animation: elsyia-pulse 1.4s ease-in-out infinite; }
        .elsyia-orb-thinking { background: radial-gradient(circle at 35% 35%, #a06bff, #3a1f6e);
          box-shadow: 0 0 64px rgba(160,110,255,0.6); animation: elsyia-spin 2.4s linear infinite; }
        .elsyia-orb-speaking { background: radial-gradient(circle at 35% 35%, #37e0a0, #0e5c3d);
          box-shadow: 0 0 64px rgba(60,224,160,0.55); animation: elsyia-pulse 0.9s ease-in-out infinite; }
        @keyframes elsyia-pulse { 0%,100% { transform: scale(1.04);} 50% { transform: scale(1.12);} }
        @keyframes elsyia-spin { from { filter: hue-rotate(0deg);} to { filter: hue-rotate(360deg);} }
        .elsyia-status { font-size: 12px; letter-spacing: 0.22em; color: #8b8ba3; text-transform: uppercase; min-height: 18px; }
        .elsyia-text { width: 100%; margin-top: 14px; max-height: 220px; overflow-y: auto; }
        .elsyia-transcript { font-size: 13px; color: #9a9ab0; font-style: italic; margin-bottom: 8px; }
        .elsyia-reply { font-size: 16px; line-height: 1.55; color: #f2f2f5; }
        .elsyia-chips { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
        .elsyia-chip { font-size: 11px; letter-spacing: 0.08em; padding: 5px 12px; border-radius: 999px;
          background: rgba(120,140,255,0.14); border: 1px solid rgba(120,140,255,0.35); color: #b9c6ff; }
        .elsyia-timing { margin-top: 10px; font-size: 11px; color: #6d6d85; letter-spacing: 0.06em; }
        .elsyia-error { margin-top: 10px; font-size: 13px; color: #ff9d9d; }
        .elsyia-ptt { margin-top: auto; width: 100%; padding: 14px; border-radius: 16px; border: none;
          font-size: 15px; font-weight: 600; letter-spacing: 0.04em; cursor: pointer;
          background: linear-gradient(135deg, #4f7cff, #8a5cff); color: white; }
        .elsyia-ptt:active { transform: scale(0.98); }
        .elsyia-confirm { display: flex; gap: 10px; width: 100%; margin-top: 12px; }
        .elsyia-confirm button { flex: 1; padding: 12px; border-radius: 14px; border: none;
          font-size: 14px; font-weight: 600; cursor: pointer; }
        .elsyia-confirm-yes { background: #2fbf71; color: #06130c; }
        .elsyia-confirm-no { background: rgba(255,255,255,0.1); color: #f2f2f5; }
        .elsyia-hint { margin-top: 10px; font-size: 11px; color: #6d6d85; }
        .elsyia-rec { display: inline-block; width: 9px; height: 9px; border-radius: 50%;
          background: #ff5d5d; margin-right: 8px;
          box-shadow: 0 0 12px rgba(255,93,93,0.8);
          animation: elsyia-pulse 1s ease-in-out infinite; }
        .elsyia-ptt-rec { background: linear-gradient(135deg, #e05252, #b03030); }
        .elsyia-dictate-preview { width: 100%; margin-top: 14px; padding: 14px;
          border-radius: 16px; background: rgba(120,140,255,0.08);
          border: 1px solid rgba(120,140,255,0.25); box-sizing: border-box;
          -webkit-app-region: no-drag; }
        .elsyia-dictate-label { font-size: 11px; letter-spacing: 0.22em; color: #8b8ba3;
          text-transform: uppercase; margin-bottom: 8px; }
        .elsyia-dictate-text { font-size: 15px; line-height: 1.55; color: #f2f2f5;
          max-height: 150px; overflow-y: auto; margin-bottom: 4px; }
        .elsyia-wake { width: 100%; margin-top: 12px; padding: 10px 12px; border-radius: 12px;
          background: rgba(120,140,255,0.07); border: 1px solid rgba(120,140,255,0.18);
          box-sizing: border-box; -webkit-app-region: no-drag; }
        .elsyia-wake-label { display: flex; align-items: center; gap: 10px; font-size: 12px;
          color: #b9c6ff; cursor: pointer; letter-spacing: 0.04em; }
        .elsyia-wake-warn { margin-top: 6px; font-size: 11px; color: #ff9d9d; }
        .elsyia-agent { width: 100%; margin-top: 12px; -webkit-app-region: no-drag; }
        .elsyia-agent-toggle { background: none; border: none; color: #8b8ba3;
          font-size: 12px; letter-spacing: 0.06em; cursor: pointer; padding: 4px 0; }
        .elsyia-agent-panel { margin-top: 8px; padding: 12px; border-radius: 12px;
          background: rgba(120,140,255,0.07); border: 1px solid rgba(120,140,255,0.18);
          box-sizing: border-box; }
        .elsyia-agent-row { display: flex; gap: 8px; }
        .elsyia-agent-input { flex: 1; background: rgba(255,255,255,0.06);
          border: 1px solid rgba(255,255,255,0.12); border-radius: 10px;
          color: #f2f2f5; padding: 10px 12px; font-size: 13px; outline: none;
          -webkit-app-region: no-drag; }
        .elsyia-agent-run { padding: 10px 16px; border-radius: 10px; border: none;
          font-weight: 600; cursor: pointer;
          background: linear-gradient(135deg, #4f7cff, #8a5cff); color: white; }
        .elsyia-agent-run:disabled { opacity: 0.5; cursor: default; }
        /* [elsyia-see] Screen-aware mode: reuses the overlay's panel/input/
           chip language — thumbnail preview, privacy microcopy, Q&A row. */
        .elsyia-see { width: 100%; margin-top: 14px; -webkit-app-region: no-drag; }
        .elsyia-see-thumb { padding: 12px; border-radius: 16px;
          background: rgba(120,140,255,0.08);
          border: 1px solid rgba(120,140,255,0.25); box-sizing: border-box; }
        .elsyia-see-thumb img { width: 100%; border-radius: 10px; display: block;
          margin-top: 8px; }
        .elsyia-see-privacy { margin-top: 8px; font-size: 11px; color: #6d6d85;
          letter-spacing: 0.06em; }
        .elsyia-see-row { display: flex; gap: 8px; margin-top: 10px; }
        .elsyia-chip-btn { cursor: pointer; font: inherit; }
      `}</style>

      <div className="elsyia-title">ELSYIA</div>
      <div className={`elsyia-orb ${orbClass}`} />
      <div className="elsyia-status">
        {dictateMode && dictateRecording && (
          <span>
            <span className="elsyia-rec" />
            dictating — hotkey to finish · Esc cancels
          </span>
        )}
        {dictateMode && !dictateRecording && dictateBusy && "cleaning up…"}
        {dictateMode && !dictateRecording && !dictateBusy && dictateText && "ready to type"}
        {!dictateMode && agentMode && agentBusy && "running the plan…"}
        {!dictateMode && status === "idle" && "hold space to talk"}
        {!dictateMode && status === "listening" && "listening…"}
        {!dictateMode && status === "thinking" && "thinking…"}
        {!dictateMode && status === "speaking" && "speaking…"}
      </div>

      <div className="elsyia-text">
        {transcript && <div className="elsyia-transcript">“{transcript}”</div>}
        {reply && <div className="elsyia-reply">{reply}</div>}
        {actions.length > 0 && (
          <div className="elsyia-chips">
            {actions.map((a, i) => (
              <span key={i} className="elsyia-chip">
                {ACTION_LABELS[a.tool] ?? a.tool}
                {a.status === "error" ? " · failed" : ""}
                {a.confirmation_required ? " · confirm?" : ""}
              </span>
            ))}
          </div>
        )}
        {typeof totalMs === "number" && (
          <div className="elsyia-timing">answered in {(totalMs / 1000).toFixed(1)}s</div>
        )}
        {error && <div className="elsyia-error">{error}</div>}
      </div>

      {seeMode ? (
        <div className="elsyia-see">
          {seeThumb && (
            <div className="elsyia-see-thumb">
              <div className="elsyia-dictate-label">screen capture</div>
              <img src={seeThumb} alt="Selected screen region" />
              <div className="elsyia-see-privacy">Elsyia only looks when you ask.</div>
            </div>
          )}
          <div className="elsyia-dictate-label" style={{ marginTop: 12 }}>
            what about it?
          </div>
          <div className="elsyia-see-row">
            <input
              className="elsyia-agent-input"
              value={seeQuestion}
              onChange={(e) => setSeeQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") void askSee(seeQuestion);
              }}
              placeholder="e.g. what is this error? · solve 2x+7=15"
              disabled={seeBusy}
              aria-label="Question about the screen capture"
            />
            <button
              className="elsyia-agent-run"
              onClick={() => void askSee(seeQuestion)}
              disabled={seeBusy || !seeQuestion.trim()}
            >
              {seeBusy ? "…" : "Ask"}
            </button>
          </div>
          <div className="elsyia-see-row">
            <button
              className="elsyia-chip elsyia-chip-btn"
              onClick={() => void askSeeByVoice()}
              disabled={seeBusy}
            >
              {seeVoiceAsking ? "Stop & ask" : "Ask by voice"}
            </button>
            <button className="elsyia-chip elsyia-chip-btn" onClick={exitSeeMode}>
              Close
            </button>
          </div>
          {seeAnswer && (
            <div className="elsyia-reply" style={{ marginTop: 12 }}>
              {seeAnswer}
            </div>
          )}
          {seeMs != null && (
            <div className="elsyia-timing">
              answered in {(seeMs / 1000).toFixed(1)}s
            </div>
          )}
          {seeAnswer && seeOk && (
            <div className="elsyia-chips">
              <button
                className="elsyia-chip elsyia-chip-btn"
                onClick={doItWithAgent}
                disabled={!seeQuestion.trim()}
              >
                Do it with agent mode
              </button>
            </div>
          )}
        </div>
      ) : dictateMode ? (
        <>
          {dictateText && !dictateRecording && !dictateBusy && (
            <div className="elsyia-dictate-preview">
              <div className="elsyia-dictate-label">cleaned & ready to type</div>
              <div className="elsyia-dictate-text">{dictateText}</div>
              <div className="elsyia-confirm">
                <button
                  className="elsyia-confirm-yes"
                  onClick={() => void typeDictation(dictateText)}
                >
                  Type it
                </button>
                <button className="elsyia-confirm-no" onClick={() => void startDictation()}>
                  Re-record
                </button>
                <button className="elsyia-confirm-no" onClick={() => void cancelDictation()}>
                  Cancel
                </button>
              </div>
            </div>
          )}
          {dictateRecording && (
            <button className="elsyia-ptt elsyia-ptt-rec" onClick={() => void finishDictation()}>
              Stop & clean up
            </button>
          )}
          {!dictateAvailable && (
            <div className="elsyia-wake-warn">
              typing needs the pynput package on the backend
            </div>
          )}
        </>
      ) : pendingConfirm ? (
        <div className="elsyia-confirm">
          <button className="elsyia-confirm-yes" onClick={() => void confirmAction()}>
            Yes, do it
          </button>
          <button
            className="elsyia-confirm-no"
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
          className="elsyia-ptt"
          onMouseDown={() => void startListening()}
          onMouseUp={() => void stopListeningAndRespond()}
          onMouseLeave={() => {
            if (status === "listening") void stopListeningAndRespond();
          }}
        >
          {status === "listening" ? "Release to send" : "Hold to talk to Elsyia"}
        </button>
      )}
      <div className="elsyia-wake">
        <label className="elsyia-wake-label">
          <input
            type="checkbox"
            checked={wakeOn}
            onChange={() => void toggleWakeWord()}
            aria-label="Wake word listener"
          />
          <span>Wake word · “{wakeModel}”</span>
        </label>
        {!wakeAvailable && (
          <div className="elsyia-wake-warn">listener unavailable on this machine</div>
        )}
      </div>
      <div className="elsyia-agent">
        <button className="elsyia-agent-toggle" onClick={() => setAgentMode((m) => !m)}>
          {agentMode ? "▾ Agent mode" : "▸ Agent mode — several things at once"}
        </button>
        {agentMode && (
          <div className="elsyia-agent-panel">
            <div className="elsyia-agent-row">
              <input
                className="elsyia-agent-input"
                value={agentInput}
                onChange={(e) => setAgentInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") void runAgent();
                }}
                placeholder="e.g. grab my flight info from Gmail and put it on my calendar"
                disabled={agentBusy}
                aria-label="Agent mode command"
              />
              <button
                className="elsyia-agent-run"
                onClick={() => void runAgent()}
                disabled={agentBusy || !agentInput.trim()}
              >
                {agentBusy ? "…" : "Run"}
              </button>
            </div>
            {agentSteps.length > 0 && (
              <div className="elsyia-chips">
                {agentSteps.map((s) => (
                  <span key={s.seq} className="elsyia-chip">
                    {s.say}{" "}
                    {s.status === "completed"
                      ? "✓"
                      : s.status === "failed"
                        ? "✗"
                        : s.status === "awaiting_confirmation"
                          ? "· confirm?"
                          : s.status === "skipped"
                            ? "· skipped"
                            : s.status === "running"
                              ? "…"
                              : ""}
                  </span>
                ))}
              </div>
            )}
            {agentPending && (
              <>
                <div className="elsyia-hint">{agentPending.message}</div>
                <div className="elsyia-confirm">
                  <button
                    className="elsyia-confirm-yes"
                    onClick={() => void confirmAgentRun()}
                  >
                    Yes, continue
                  </button>
                  <button
                    className="elsyia-confirm-no"
                    onClick={() => void denyAgentRun()}
                  >
                    No
                  </button>
                </div>
              </>
            )}
          </div>
        )}
      </div>
      <div className="elsyia-hint">
        Ctrl+Shift+J summon · Ctrl+Shift+D dictate · Esc dismiss
      </div>
    </div>
  );
}
