/**
 * Elysia Electron main process.
 *
 * - Main window: the full Elysia desktop.
 * - Jev overlay: a small always-on-top summon window, toggled from
 *   anywhere with the global hotkey Ctrl+Shift+J (Cmd+Shift+J on macOS).
 *   The overlay runs Jev's tight voice loop (mic -> Whisper -> Ollama
 *   -> actions -> TTS) through the backend /jev endpoints.
 */
import { app, BrowserWindow, desktopCapturer, dialog, globalShortcut, ipcMain, screen, session, shell } from "electron";
import path from "node:path";
import { fileURLToPath } from "node:url";
// [jev-packaging] Desktop-app modules: backend supervisor, tray, first-run.
import { getBackendUrl, startBackend, stopBackend } from "./backend-launcher.js";
import { getSetting, setSetting } from "./app-settings.js";
import { applyStoredLoginSetting, createTray, refreshTrayMenu, registerWakeWordControl } from "./tray.js";
import { isOllamaReachable, showSetupWindow } from "./first-run.js";
// [jev-dictation] Global hotkey module (say it, it types). Additive — the
// overlay owns the record/stop/type toggle state; main only forwards presses.
import { registerDictationHotkey } from "./dictation.js";
// [jev-see] Screen-aware hotkey module (circle anything, then just ask).
// Additive — main only forwards the press and performs the explicit
// region capture; the overlay owns the Q&A UI.
import { registerSeeHotkey, normalizeRect, toCropBounds } from "./see.js";
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const isDev = !app.isPackaged;
const JEV_HOTKEY = "CommandOrControl+Shift+J";
let mainWindow = null;
let jevOverlay = null;
function createMainWindow() {
    mainWindow = new BrowserWindow({
        width: 1100,
        height: 750,
        minWidth: 720,
        minHeight: 480,
        backgroundColor: "#05050a",
        frame: false,
        titleBarStyle: "hidden",
        webPreferences: {
            preload: path.join(__dirname, "preload.cjs"),
            contextIsolation: true,
            nodeIntegration: false,
        },
    });
    if (isDev) {
        mainWindow.loadURL("http://localhost:5173");
        mainWindow.webContents.openDevTools({ mode: "detach" });
    }
    else {
        mainWindow.loadFile(path.join(__dirname, "../dist/index.html"));
    }
    mainWindow.on("closed", () => {
        mainWindow = null;
    });
}
function createJevOverlay() {
    jevOverlay = new BrowserWindow({
        width: 400,
        height: 580,
        minWidth: 360,
        minHeight: 480,
        backgroundColor: "#00000000",
        frame: false,
        transparent: true,
        alwaysOnTop: true,
        skipTaskbar: true,
        resizable: false,
        show: false,
        webPreferences: {
            preload: path.join(__dirname, "preload.cjs"),
            contextIsolation: true,
            nodeIntegration: false,
        },
    });
    if (isDev) {
        jevOverlay.loadURL("http://localhost:5173/?overlay=jev");
    }
    else {
        jevOverlay.loadFile(path.join(__dirname, "../dist/index.html"), {
            query: { overlay: "jev" },
        });
    }
    jevOverlay.on("closed", () => {
        jevOverlay = null;
    });
    return jevOverlay;
}
/** Toggle the Jev overlay from anywhere in the OS. */
function summonJev(wake = false) {
    const win = jevOverlay ?? createJevOverlay();
    if (win.isVisible()) {
        win.hide();
    }
    else {
        win.show();
        win.focus();
        win.webContents.send("jev-summon", { wake });
    }
}
/**
 * [jev-see] Screen-aware region select.
 *
 * A fullscreen transparent window where the user drags a rectangle
 * (Esc cancels). The selection is captured via desktopCapturer, POSTed
 * to the backend as the current explicit capture, and the Jev overlay
 * opens in see-mode. THIS IS THE ONLY SCREEN-CAPTURE PATH IN JEV —
 * there is no background watching and no ambient screenshots anywhere.
 */
let seeSelectWindow = null;
function openSeeSelect() {
    if (seeSelectWindow) {
        seeSelectWindow.focus();
        return;
    }
    const display = screen.getPrimaryDisplay();
    seeSelectWindow = new BrowserWindow({
        x: display.bounds.x,
        y: display.bounds.y,
        width: display.bounds.width,
        height: display.bounds.height,
        frame: false,
        transparent: true,
        alwaysOnTop: true,
        skipTaskbar: true,
        resizable: false,
        show: false,
        webPreferences: {
            preload: path.join(__dirname, "preload.cjs"),
            contextIsolation: true,
            nodeIntegration: false,
        },
    });
    if (isDev) {
        seeSelectWindow.loadURL("http://localhost:5173/?overlay=see");
    }
    else {
        seeSelectWindow.loadFile(path.join(__dirname, "../dist/index.html"), {
            query: { overlay: "see" },
        });
    }
    // Above screen-savers and fullscreen apps: a capture must always win.
    seeSelectWindow.setAlwaysOnTop(true, "screen-saver");
    seeSelectWindow.show();
    seeSelectWindow.on("closed", () => {
        seeSelectWindow = null;
    });
}
async function handleSeeRegion(rect) {
    const win = seeSelectWindow;
    seeSelectWindow = null;
    win?.close();
    try {
        const display = screen.getPrimaryDisplay();
        const scale = display.scaleFactor || 1;
        const sources = await desktopCapturer.getSources({
            types: ["screen"],
            thumbnailSize: {
                width: Math.round(display.size.width * scale),
                height: Math.round(display.size.height * scale),
            },
        });
        const source = sources.find((s) => s.display_id === String(display.id)) ?? sources[0];
        if (!source)
            throw new Error("No screen source available.");
        const cropped = source.thumbnail.crop(toCropBounds(normalizeRect({ x: rect.x, y: rect.y }, { x: rect.x + rect.width, y: rect.y + rect.height }), scale));
        const png = cropped.toPNG();
        // Store as the current explicit capture (the only write path).
        const form = new FormData();
        form.append("file", new Blob([new Uint8Array(png)]), "capture.png");
        const res = await fetch(`${getBackendUrl()}/api/v1/jev/see/capture`, {
            method: "POST",
            body: form,
        });
        if (!res.ok)
            throw new Error(`Capture upload failed: ${res.status}`);
        // Summon the overlay in see-mode with a thumbnail of the region.
        const overlay = jevOverlay ?? createJevOverlay();
        if (!overlay.isVisible())
            overlay.show();
        overlay.focus();
        overlay.webContents.send("jev-summon", {
            wake: false,
            see: true,
            thumbnail: `data:image/png;base64,${png.toString("base64")}`,
        });
    }
    catch (err) {
        console.error("[Jev] Screen capture failed:", err);
        dialog.showErrorBox("Jev — screen capture failed", err instanceof Error ? err.message : String(err));
    }
}
/**
 * Wake-word polling: while the listener toggle is on, ask the backend
 * twice a second whether the wake phrase was heard. A hit summons Jev
 * exactly like the global hotkey, flagged as a hands-free wake.
 *
 * [jev-packaging] The backend URL is dynamic in the packaged app (the
 * launcher picks a free loopback port), so it is resolved per poll.
 */
const wakePollUrl = () => `${getBackendUrl()}/api/v1/jev/wakeword/event`;
let wakePollTimer = null;
/** [jev-packaging] Main-process view of the wake-word switch (tray + overlay sync). */
let wakeWordOn = false;
async function pollWakeWord() {
    try {
        const res = await fetch(wakePollUrl());
        if (!res.ok)
            return;
        const data = (await res.json());
        if (data.wake) {
            console.log("[Jev] Wake word heard — summoning");
            summonJev(true);
        }
    }
    catch {
        // Backend not up (yet) — stay quiet and keep polling.
    }
}
function setWakeWordPolling(enabled) {
    if (wakePollTimer) {
        clearInterval(wakePollTimer);
        wakePollTimer = null;
    }
    if (enabled) {
        console.log("[Jev] Wake-word polling started");
        wakePollTimer = setInterval(() => void pollWakeWord(), 500);
    }
    else {
        console.log("[Jev] Wake-word polling stopped");
    }
}
/**
 * [jev-packaging] Central wake-word switch: drives the backend listener
 * service, the main-process poller, the persisted setting, the overlay
 * checkbox and the tray menu from one place.
 */
async function setWakeWordEnabled(on) {
    wakeWordOn = on;
    setWakeWordPolling(on);
    setSetting("wakeWordEnabled", on);
    try {
        await fetch(`${getBackendUrl()}/api/v1/jev/wakeword/${on ? "enable" : "disable"}`, {
            method: "POST",
        });
    }
    catch {
        // Backend not up yet — the overlay retries on its next toggle/status fetch.
    }
    for (const win of BrowserWindow.getAllWindows()) {
        win.webContents.send("jev-wakeword-state", on);
    }
    refreshTrayMenu();
}
app.whenReady().then(async () => {
    session.defaultSession.setPermissionRequestHandler((_webContents, _permission, callback) => {
        callback(true);
    });
    session.defaultSession.setPermissionCheckHandler(() => true);
    // [jev-packaging] Boot the backend first; a real error dialog, never a blank screen.
    try {
        const url = await startBackend();
        console.log(`[Jev] backend ready at ${url}`);
    }
    catch (err) {
        console.error(`[Jev] backend failed to start: ${err}`);
        // startBackend already showed the error dialog.
        app.quit();
        return;
    }
    // [jev-packaging] Tray icon + start-at-login, and the wake-word tray hook.
    createTray({ onSummon: () => summonJev(false) });
    registerWakeWordControl({
        isEnabled: () => wakeWordOn,
        setEnabled: (on) => void setWakeWordEnabled(on),
    });
    applyStoredLoginSetting();
    if (getSetting("wakeWordEnabled", false)) {
        void setWakeWordEnabled(true);
    }
    const registered = globalShortcut.register(JEV_HOTKEY, () => summonJev(false));
    if (!registered) {
        console.error(`[Jev] Failed to register global hotkey ${JEV_HOTKEY}`);
    }
    else {
        console.log(`[Jev] Global hotkey registered: ${JEV_HOTKEY}`);
    }
    // [jev-dictation] Say-it-it-types hotkey (default Ctrl+Shift+D, override
    // with JEV_DICTATION_HOTKEY). Forwards to the overlay, which toggles
    // recording -> stop/process -> preview -> type into the focused app.
    registerDictationHotkey({
        onToggle: () => {
            const win = jevOverlay ?? createJevOverlay();
            if (!win.isVisible())
                win.show();
            win.webContents.send("jev-summon", { wake: false, dictate: true });
        },
    });
    // [jev-see] Screen-aware hotkey (default Ctrl+Shift+S, override with
    // JEV_SEE_HOTKEY). Opens the region-select overlay — the ONLY trigger
    // for screen capture. Jev never screenshots in the background.
    registerSeeHotkey({ onPress: () => openSeeSelect() });
    ipcMain.on("jev-see-region", (_event, rect) => {
        void handleSeeRegion(rect);
    });
    ipcMain.on("jev-see-cancel", () => {
        seeSelectWindow?.close();
    });
    ipcMain.on("jev-hide-overlay", () => {
        jevOverlay?.hide();
    });
    ipcMain.on("jev-wakeword-polling", (_event, enabled) => {
        void setWakeWordEnabled(enabled === true);
    });
    ipcMain.on("jev-open-external", (_event, url) => {
        if (typeof url === "string" && /^https?:\/\//.test(url)) {
            shell.openExternal(url);
        }
    });
    // [jev-packaging] First-run: Ollama check before showing the desktop.
    // Jev's brain is not bundled (multi-GB weights), so guide the install.
    if (await isOllamaReachable()) {
        createMainWindow();
    }
    else {
        console.log("[Jev] Ollama not reachable — showing first-run setup");
        showSetupWindow(path.join(__dirname, "preload.cjs"), () => createMainWindow());
    }
});
app.on("will-quit", () => {
    if (wakePollTimer) {
        clearInterval(wakePollTimer);
        wakePollTimer = null;
    }
    stopBackend(); // [jev-packaging] kill the backend child process
    globalShortcut.unregisterAll();
});
app.on("window-all-closed", () => {
    if (process.platform !== "darwin")
        app.quit();
});
app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0)
        createMainWindow();
});
