import { useEffect } from "react";
import ElysiaOrb from "@/components/Orb";
import { useVoiceAssistant } from "@/hooks/useVoiceAssistant";

/**
 * Elysia's main window. Phase 1: the orb is the whole surface — no chat
 * list, no message bubbles. Push-to-talk is bound to holding Space
 * (not typing-safe yet — fine for Phase 1's single-window, no-text-input
 * UI; revisit if a text input is ever added alongside voice).
 */
export default function App() {
  const { status, lastError, startListening, stopListeningAndRespond, forceResetToIdle, isRecording } = useVoiceAssistant();

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.code === "Space") {
        e.preventDefault();
        if (!e.repeat && status === "idle") {
          void startListening();
        }
      }
      if (e.code === "Escape") {
        e.preventDefault();
        if (status !== "idle") {
          void forceResetToIdle();
        }
      }
    };
    const onKeyUp = (e: KeyboardEvent) => {
      if (e.code === "Space") {
        e.preventDefault();
        if (isRecording()) {
          void stopListeningAndRespond();
        }
      }
    };
    const onBlur = () => {
      if (isRecording()) {
        void stopListeningAndRespond();
      }
    };

    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    window.addEventListener("blur", onBlur);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("keyup", onKeyUp);
      window.removeEventListener("blur", onBlur);
    };
  }, [startListening, stopListeningAndRespond, isRecording, status]);

  return (
    <div className="w-screen h-screen overflow-hidden bg-void">
      <ElysiaOrb assistantStatus={status} />
      {lastError && (
        <div className="fixed bottom-24 left-1/2 -translate-x-1/2 text-xs text-red-300 bg-black/50 px-3 py-2 rounded-lg backdrop-blur">
          {lastError}
        </div>
      )}
      <div className="fixed bottom-6 left-1/2 -translate-x-1/2 text-[11px] tracking-widest opacity-40">
        HOLD SPACE TO TALK · ESC TO CANCEL
      </div>
    </div>
  );
}
