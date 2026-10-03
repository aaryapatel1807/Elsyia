/**
 * Voice client — the frontend half of Stage 3.
 *
 * Push-to-talk flow:
 *   1. startRecording() while the key/button is held
 *   2. stopRecording() on release → audio blob (webm/opus, whatever
 *      MediaRecorder's default is in Electron/Chromium)
 *   3. transcribe() → POST /api/v1/voice/transcribe → user's text
 *      (faster-whisper decodes webm directly via PyAV, no client-side
 *      conversion to WAV needed)
 *   4. (caller sends that text to /api/v1/chat as usual)
 *   5. speak(responseText) → POST /api/v1/voice/speak → plays the reply
 *
 * Kept deliberately separate from the orb component: this module only
 * knows about audio I/O and the backend, the orb only knows about
 * assistantStatus. A hook (useVoiceAssistant, added alongside this file)
 * is what connects the two.
 */

import { apiBase } from "./api";

const API_BASE = apiBase();

export class VoiceRecorder {
  private mediaRecorder: MediaRecorder | null = null;
  private chunks: Blob[] = [];
  private stream: MediaStream | null = null;

  async start(): Promise<void> {
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    this.chunks = [];
    this.mediaRecorder = new MediaRecorder(this.stream);
    this.mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) this.chunks.push(e.data);
    };
    this.mediaRecorder.start(100);
  }

  /** Stops recording and returns the captured audio as a Blob. */
  async stop(): Promise<Blob> {
    return new Promise((resolve, reject) => {
      if (!this.mediaRecorder) {
        reject(new Error("Recording was never started."));
        return;
      }
      this.mediaRecorder.onstop = () => {
        const blob = new Blob(this.chunks, { type: this.mediaRecorder?.mimeType || "audio/webm" });
        this.stream?.getTracks().forEach((track) => track.stop());
        this.stream = null;
        this.mediaRecorder = null;
        resolve(blob);
      };
      this.mediaRecorder.stop();
    });
  }
}

/** Sends a recorded audio blob to the backend and returns the transcript. */
export async function transcribe(audio: Blob): Promise<string> {
  const form = new FormData();
  form.append("audio", audio, "recording.webm");

  const response = await fetch(`${API_BASE}/voice/transcribe`, {
    method: "POST",
    body: form,
  });

  if (!response.ok) {
    throw new Error(`Transcription failed: ${response.status} ${await response.text()}`);
  }

  const data = (await response.json()) as { text: string };
  return data.text;
}

/** Requests speech synthesis for the given text and plays it back. */
export async function speak(text: string): Promise<void> {
  const response = await fetch(`${API_BASE}/voice/speak`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });

  if (!response.ok) {
    throw new Error(`Speech synthesis failed: ${response.status} ${await response.text()}`);
  }

  const audioBlob = await response.blob();
  const audioUrl = URL.createObjectURL(audioBlob);
  const audioEl = new Audio(audioUrl);

  await new Promise<void>((resolve, reject) => {
    audioEl.onended = () => {
      URL.revokeObjectURL(audioUrl);
      resolve();
    };
    audioEl.onerror = () => {
      URL.revokeObjectURL(audioUrl);
      reject(new Error("Audio playback failed."));
    };
    void audioEl.play();
  });
}

/** Fetches synthesized speech and returns an Object URL (does not play it). */
export async function fetchSpeechUrl(text: string): Promise<string> {
  const response = await fetch(`${API_BASE}/voice/speak`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });

  if (!response.ok) {
    throw new Error(`Speech synthesis failed: ${response.status} ${await response.text()}`);
  }

  const audioBlob = await response.blob();
  return URL.createObjectURL(audioBlob);
}

/** Manages sequential playback of multiple audio chunks. */
export class AudioQueue {
  private queue: string[] = [];
  private isPlaying = false;
  private currentAudio: HTMLAudioElement | null = null;
  public onComplete?: () => void;

  enqueue(audioUrl: string) {
    this.queue.push(audioUrl);
    this.playNext();
  }

  private playNext() {
    if (this.isPlaying || this.queue.length === 0) return;
    
    this.isPlaying = true;
    const url = this.queue.shift()!;
    this.currentAudio = new Audio(url);
    
    this.currentAudio.onended = () => {
      URL.revokeObjectURL(url);
      this.currentAudio = null;
      this.isPlaying = false;
      if (this.queue.length > 0) {
        this.playNext();
      } else {
        this.onComplete?.();
      }
    };
    
    this.currentAudio.onerror = (e) => {
      console.error("Audio playback failed for chunk:", e);
      URL.revokeObjectURL(url);
      this.currentAudio = null;
      this.isPlaying = false;
      this.playNext(); // skip and try next
    };
    
    void this.currentAudio.play();
  }

  stop() {
    if (this.currentAudio) {
      this.currentAudio.pause();
      this.currentAudio = null;
    }
    for (const url of this.queue) {
      URL.revokeObjectURL(url);
    }
    this.queue = [];
    this.isPlaying = false;
  }
}
