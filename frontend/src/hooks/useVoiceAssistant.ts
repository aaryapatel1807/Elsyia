import { useCallback, useRef, useState } from "react";
import { VoiceRecorder, speak, transcribe, AudioQueue, fetchSpeechUrl } from "@/lib/voice";
import type { AssistantStatus } from "@/components/Orb";
import { apiBase } from "../lib/api";

const API_BASE = apiBase();
const MAX_RECORDING_MS = 15000;

interface ChatApiResponse {
  response: string;
  conversation_id: string;
}

interface ToolResult {
  status: string;
  tool_name: string;
  result?: unknown;
  error?: string | null;
  confirmation_required?: boolean;
  confirmation_message?: string | null;
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
  const [toolResult, setToolResult] = useState<ToolResult | null>(null);

  const recorderRef = useRef<VoiceRecorder | null>(null);
  const conversationIdRef = useRef<string | undefined>(undefined);
  const autoStopTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const audioQueueRef = useRef<AudioQueue | null>(null);

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
          stream: true,
        }),
      });
      if (!chatResponse.ok) {
        throw new Error(`Chat request failed: ${chatResponse.status}`);
      }

      setStatus("speaking");
      setReply("");
      setToolResult(null);

      const reader = chatResponse.body?.getReader();
      const decoder = new TextDecoder("utf-8");
      let fullReply = "";
      let currentSentence = "";
      let accumulatedChunk = "";
      
      const audioQueue = new AudioQueue();
      audioQueue.onComplete = () => {
        setStatus("idle");
      };
      audioQueueRef.current = audioQueue;

      if (reader) {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          accumulatedChunk += decoder.decode(value, { stream: true });
          
          let lines = accumulatedChunk.split('\n');
          accumulatedChunk = lines.pop() || ''; 
          
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const dataStr = line.slice(6);
              try {
                const data = JSON.parse(dataStr);
                if (data.type === 'token') {
                  fullReply += data.content;
                  setToolResult(null);
                  currentSentence += data.content;
                  setReply(fullReply);
                  
                  // Sentence boundary detection (now including commas for ultra-fast first response)
                  if (/[.,!?:](\s|\n)/.test(currentSentence) || currentSentence.split(' ').length > 12) {
                    const sentenceToSpeak = currentSentence.trim();
                    currentSentence = ""; 
                    if (sentenceToSpeak.length > 0) {
                      fetchSpeechUrl(sentenceToSpeak).then(url => {
                        audioQueue.enqueue(url);
                      }).catch(err => console.error("Failed to fetch audio for chunk:", err));
                    }
                  }
                } else if (data.type === 'tool') {
                  const toolReply = data.content || "";
                  setReply(toolReply);
                  setToolResult(data.tool_result || null);
                  if (toolReply.trim()) {
                    fetchSpeechUrl(toolReply).then(url => {
                      audioQueue.enqueue(url);
                    }).catch(err => console.error("Failed to fetch tool result audio:", err));
                  }
                } else if (data.type === 'done') {
                  conversationIdRef.current = data.conversation_id;
                  if (currentSentence.trim().length > 0) {
                    fetchSpeechUrl(currentSentence.trim()).then(url => {
                      audioQueue.enqueue(url);
                    }).catch(err => console.error("Failed to fetch audio for chunk:", err));
                  }
                } else if (data.type === 'error') {
                  console.error("LLM Error:", data.error);
                }
              } catch (e) {
                console.error("Failed to parse SSE data:", dataStr);
              }
            }
          }
        }
      }
    } catch (err) {
      setLastError(err instanceof Error ? err.message : "Voice pipeline failed.");
      setStatus("idle");
    }
  }, []);

  const forceResetToIdle = useCallback(async () => {
    const recorder = recorderRef.current;
    recorderRef.current = null;

    if (autoStopTimeoutRef.current) {
      clearTimeout(autoStopTimeoutRef.current);
      autoStopTimeoutRef.current = null;
    }

    if (recorder) {
      try {
        await recorder.stop();
      } catch (e) {
        console.error("Failed to stop recorder during force reset", e);
      }
    }

    if (audioQueueRef.current) {
      audioQueueRef.current.stop();
      audioQueueRef.current = null;
    }

    setStatus("idle");
    setLastError(null);
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

  return { status, transcript, reply, toolResult, lastError, startListening, stopListeningAndRespond, forceResetToIdle, isRecording };
}
