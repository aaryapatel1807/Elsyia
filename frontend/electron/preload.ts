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
});
