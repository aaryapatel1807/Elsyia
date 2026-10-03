/**
 * Preload bridge. Minimal, explicit contextBridge APIs only —
 * never a raw ipcRenderer passthrough.
 */
import { contextBridge, ipcRenderer } from "electron";

export interface JevSummonInfo {
  /** True when the summon came from the wake-word listener (hands-free). */
  wake: boolean;
}

contextBridge.exposeInMainWorld("elysia", {
  version: "0.1.0",
  /** Fired when the global Jev hotkey (or wake word) summons the overlay. */
  onJevSummon: (callback: (info?: JevSummonInfo) => void): (() => void) => {
    const listener = (_event: unknown, info?: JevSummonInfo) => callback(info);
    ipcRenderer.on("jev-summon", listener);
    return () => ipcRenderer.removeListener("jev-summon", listener);
  },
  /** Ask the main process to hide the Jev overlay window. */
  hideJevOverlay: (): void => {
    ipcRenderer.send("jev-hide-overlay");
  },
  /** Tell the main process to start/stop polling the backend wake-word event. */
  setWakeWordPolling: (enabled: boolean): void => {
    ipcRenderer.send("jev-wakeword-polling", enabled);
  },
  /**
   * Backend base URL chosen by the main process (a free loopback port in
   * the packaged app; the dev uvicorn URL otherwise). The renderer must
   * use this instead of a hardcoded port.
   */
  backendUrl: (): string => process.env.JEV_BACKEND_URL ?? "http://127.0.0.1:8000",
  /** First-run setup screen: re-check Ollama reachability. */
  retrySetup: (): void => {
    ipcRenderer.send("jev-setup-retry");
  },
  /** First-run setup screen: result of the Ollama re-check. */
  onSetupStatus: (callback: (ok: boolean) => void): (() => void) => {
    const listener = (_event: unknown, ok: boolean) => callback(ok);
    ipcRenderer.on("jev-setup-status", listener);
    return () => ipcRenderer.removeListener("jev-setup-status", listener);
  },
  /** Open a URL in the user's default browser. */
  openExternal: (url: string): void => {
    ipcRenderer.send("jev-open-external", url);
  },
  /** Fired when the wake-word switch changes (e.g. from the tray menu). */
  onWakeWordState: (callback: (on: boolean) => void): (() => void) => {
    const listener = (_event: unknown, on: boolean) => callback(on);
    ipcRenderer.on("jev-wakeword-state", listener);
    return () => ipcRenderer.removeListener("jev-wakeword-state", listener);
  },
});
