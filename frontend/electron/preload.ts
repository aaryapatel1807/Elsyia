/**
 * Preload bridge. Nothing exposed yet in Phase 1 — the renderer talks to
 * the backend directly over HTTP (CORS-enabled FastAPI). Native bridges
 * (mic capture, desktop automation, etc.) get added here in later phases
 * behind explicit, minimal contextBridge APIs — never a raw ipcRenderer
 * passthrough.
 */
import { contextBridge } from "electron";

contextBridge.exposeInMainWorld("elysia", {
  version: "0.1.0",
});
