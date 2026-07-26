import { useCallback, useRef, useState } from "react";
import { VoiceRecorder, speak, transcribe } from "@/lib/voice";
import type { AssistantStatus } from "@/components/Orb";

const API_BASE = "http://127.0.0.1:8000/api/v1";
const MAX_RECORDING_MS = 15000;

interface ChatApiResponse {
  response: string;
  conversation_id: string;
}

/**
 * Connects push-to-talk audio capture to the backend chat + voice
 * endpoints, and exposes the assistant's current state so the orb can
 * reflect it. This is the only place that sequences
 * listening → thinking → speaking — Orb.tsx just renders whatever
 * status it's given.
 */
export function useVoiceAssistant() {
  const [status, setStatus] = useState<AssistantStatus>("idle");
  const [lastError, setLastError] = useState<string | null>(null);
  const [transcript, setTranscript] = useState<string>("");
  const [reply, setReply] = useState<string>("");

  const recorderRef = useRef<VoiceRecorder | null>(null);
  const conversationIdRef = useRef<string | undefined>(undefined);
  const autoStopTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const isRecording = useCallback(() => recorderRef.current !== null, []);

  const stopListeningAndRespond = useCallback(async () => {
    const recorder = recorderRef.current;
    if (!recorder) return;
    recorderRef.current = null;

    if (autoStopTimeoutRef.current) {
      clearTimeout(autoStopTimeoutRef.current);
      autoStopTimeoutRef.current = null;
    }

    try {
      setStatus("thinking");
      const audioBlob = await recorder.stop();

      const text = await transcribe(audioBlob);
      setTranscript(text);
      if (!text.trim()) {
        setLastError("Didn't catch that — try holding a little longer");
        setStatus("idle");
        return;
      }

      const chatResponse = await fetch(`${API_BASE}/chat/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: text,
          conversation_id: conversationIdRef.current,
          stream: false,
        }),
      });
      if (!chatResponse.ok) {
        throw new Error(`Chat request failed: ${chatResponse.status}`);
      }
      const data = (await chatResponse.json()) as ChatApiResponse;
      conversationIdRef.current = data.conversation_id;
      setReply(data.response);

      setStatus("speaking");
      await speak(data.response);
      setStatus("idle");
    } catch (err) {
      setLastError(err instanceof Error ? err.message : "Voice pipeline failed.");
      setStatus("idle");
    }
  }, []);

  const startListening = useCallback(async () => {
    if (status !== "idle") return;

    setLastError(null);
    try {
      const recorder = new VoiceRecorder();
      await recorder.start();
      recorderRef.current = recorder;
      setStatus("listening");

      autoStopTimeoutRef.current = setTimeout(() => {
        stopListeningAndRespond();
      }, MAX_RECORDING_MS);
    } catch (err) {
      setLastError(err instanceof Error ? err.message : "Microphone access failed.");
      setStatus("idle");
    }
  }, [status, stopListeningAndRespond]);

  return { status, transcript, reply, lastError, startListening, stopListeningAndRespond, isRecording };
}
