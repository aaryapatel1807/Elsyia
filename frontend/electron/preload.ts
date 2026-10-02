/**
 * Preload bridge. Minimal, explicit contextBridge APIs only —
 * never a raw ipcRenderer passthrough.
 */
import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("elysia", {
  version: "0.1.0",
  /** Fired when the global Jev hotkey summons the overlay. */
  onJevSummon: (callback: () => void): (() => void) => {
    const listener = () => callback();
    ipcRenderer.on("jev-summon", listener);
    return () => ipcRenderer.removeListener("jev-summon", listener);
  },
  /** Ask the main process to hide the Jev overlay window. */
  hideJevOverlay: (): void => {
    ipcRenderer.send("jev-hide-overlay");
  },
});
