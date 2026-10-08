"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
/**
 * Preload bridge. Minimal, explicit contextBridge APIs only —
 * never a raw ipcRenderer passthrough.
 */
const electron_1 = require("electron");
electron_1.contextBridge.exposeInMainWorld("elysia", {
    version: "0.1.0",
    /** Fired when the global Elsyia hotkey (or wake word) summons the overlay. */
    onElsyiaSummon: (callback) => {
        const listener = (_event, info) => callback(info);
        electron_1.ipcRenderer.on("elsyia-summon", listener);
        return () => electron_1.ipcRenderer.removeListener("elsyia-summon", listener);
    },
    /** Ask the main process to hide the Elsyia overlay window. */
    hideElsyiaOverlay: () => {
        electron_1.ipcRenderer.send("elsyia-hide-overlay");
    },
    /** Tell the main process to start/stop polling the backend wake-word event. */
    setWakeWordPolling: (enabled) => {
        electron_1.ipcRenderer.send("elsyia-wakeword-polling", enabled);
    },
    /**
     * Backend base URL chosen by the main process (a free loopback port in
     * the packaged app; the dev uvicorn URL otherwise). The renderer must
     * use this instead of a hardcoded port.
     */
    backendUrl: () => process.env.ELSYIA_BACKEND_URL ?? "http://127.0.0.1:8000",
    /** First-run setup screen: re-check Ollama reachability. */
    retrySetup: () => {
        electron_1.ipcRenderer.send("elsyia-setup-retry");
    },
    /** First-run setup screen: result of the Ollama re-check. */
    onSetupStatus: (callback) => {
        const listener = (_event, ok) => callback(ok);
        electron_1.ipcRenderer.on("elsyia-setup-status", listener);
        return () => electron_1.ipcRenderer.removeListener("elsyia-setup-status", listener);
    },
    /** Open a URL in the user's default browser. */
    openExternal: (url) => {
        electron_1.ipcRenderer.send("elsyia-open-external", url);
    },
    /** Fired when the wake-word switch changes (e.g. from the tray menu). */
    onWakeWordState: (callback) => {
        const listener = (_event, on) => callback(on);
        electron_1.ipcRenderer.on("elsyia-wakeword-state", listener);
        return () => electron_1.ipcRenderer.removeListener("elsyia-wakeword-state", listener);
    },
    /**
     * [elsyia-see] Region-select overlay: report the user-dragged rectangle
     * (CSS pixels, relative to the select window). This is the only path
     * that leads to a screen capture.
     */
    selectSeeRegion: (rect) => {
        electron_1.ipcRenderer.send("elsyia-see-region", rect);
    },
    /** [elsyia-see] Cancel the region select (Esc) — no capture happens. */
    cancelSeeSelect: () => {
        electron_1.ipcRenderer.send("elsyia-see-cancel");
    },
});
