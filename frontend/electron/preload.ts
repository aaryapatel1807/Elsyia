/**
 * Preload bridge. Minimal, explicit contextBridge APIs only —
 * never a raw ipcRenderer passthrough.
 */
import { contextBridge, ipcRenderer } from "electron";

export interface ElsyiaSummonInfo {
  /** True when the summon came from the wake-word listener (hands-free). */
  wake: boolean;
  /** [elsyia-dictation] True when the summon toggles dictation mode (record/type). */
  dictate?: boolean;
  /** [elsyia-see] True when the summon follows an explicit region capture. */
  see?: boolean;
  /** [elsyia-see] Data-URL thumbnail of the captured region, when see is true. */
  thumbnail?: string;
}

contextBridge.exposeInMainWorld("elysia", {
  version: "0.1.0",
  /** Fired when the global Elsyia hotkey (or wake word) summons the overlay. */
  onElsyiaSummon: (callback: (info?: ElsyiaSummonInfo) => void): (() => void) => {
    const listener = (_event: unknown, info?: ElsyiaSummonInfo) => callback(info);
    ipcRenderer.on("elsyia-summon", listener);
    return () => ipcRenderer.removeListener("elsyia-summon", listener);
  },
  /** Ask the main process to hide the Elsyia overlay window. */
  hideElsyiaOverlay: (): void => {
    ipcRenderer.send("elsyia-hide-overlay");
  },
  /** Tell the main process to start/stop polling the backend wake-word event. */
  setWakeWordPolling: (enabled: boolean): void => {
    ipcRenderer.send("elsyia-wakeword-polling", enabled);
  },
  /**
   * Backend base URL chosen by the main process (a free loopback port in
   * the packaged app; the dev uvicorn URL otherwise). The renderer must
   * use this instead of a hardcoded port.
   */
  backendUrl: (): string => process.env.ELSYIA_BACKEND_URL ?? "http://127.0.0.1:8000",
  /** First-run setup screen: re-check Ollama reachability. */
  retrySetup: (): void => {
    ipcRenderer.send("elsyia-setup-retry");
  },
  /** First-run setup screen: result of the Ollama re-check. */
  onSetupStatus: (callback: (ok: boolean) => void): (() => void) => {
    const listener = (_event: unknown, ok: boolean) => callback(ok);
    ipcRenderer.on("elsyia-setup-status", listener);
    return () => ipcRenderer.removeListener("elsyia-setup-status", listener);
  },
  /** Open a URL in the user's default browser. */
  openExternal: (url: string): void => {
    ipcRenderer.send("elsyia-open-external", url);
  },
  /** Fired when the wake-word switch changes (e.g. from the tray menu). */
  onWakeWordState: (callback: (on: boolean) => void): (() => void) => {
    const listener = (_event: unknown, on: boolean) => callback(on);
    ipcRenderer.on("elsyia-wakeword-state", listener);
    return () => ipcRenderer.removeListener("elsyia-wakeword-state", listener);
  },
  /**
   * [elsyia-see] Region-select overlay: report the user-dragged rectangle
   * (CSS pixels, relative to the select window). This is the only path
   * that leads to a screen capture.
   */
  selectSeeRegion: (rect: {
    x: number;
    y: number;
    width: number;
    height: number;
  }): void => {
    ipcRenderer.send("elsyia-see-region", rect);
  },
  /** [elsyia-see] Cancel the region select (Esc) — no capture happens. */
  cancelSeeSelect: (): void => {
    ipcRenderer.send("elsyia-see-cancel");
  },
});
