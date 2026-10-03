/**
 * Elysia Electron main process.
 *
 * - Main window: the full Elysia desktop.
 * - Jev overlay: a small always-on-top summon window, toggled from
 *   anywhere with the global hotkey Ctrl+Shift+J (Cmd+Shift+J on macOS).
 *   The overlay runs Jev's tight voice loop (mic -> Whisper -> Ollama
 *   -> actions -> TTS) through the backend /jev endpoints.
 */
import { app, BrowserWindow, dialog, globalShortcut, ipcMain, session, shell } from "electron";
import path from "node:path";
import { fileURLToPath } from "node:url";
// [jev-packaging] Desktop-app modules: backend supervisor, tray, first-run.
import { getBackendUrl, startBackend, stopBackend } from "./backend-launcher.js";
import { getSetting, setSetting } from "./app-settings.js";
import { applyStoredLoginSetting, createTray, refreshTrayMenu, registerWakeWordControl } from "./tray.js";
import { isOllamaReachable, showSetupWindow } from "./first-run.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const isDev = !app.isPackaged;
const JEV_HOTKEY = "CommandOrControl+Shift+J";

let mainWindow: BrowserWindow | null = null;
let jevOverlay: BrowserWindow | null = null;

function createMainWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1100,
    height: 750,
    minWidth: 720,
    minHeight: 480,
    backgroundColor: "#05050a",
    frame: false,
    titleBarStyle: "hidden",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  if (isDev) {
    mainWindow.loadURL("http://localhost:5173");
    mainWindow.webContents.openDevTools({ mode: "detach" });
  } else {
    mainWindow.loadFile(path.join(__dirname, "../dist/index.html"));
  }
  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

function createJevOverlay(): BrowserWindow {
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
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  if (isDev) {
    jevOverlay.loadURL("http://localhost:5173/?overlay=jev");
  } else {
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
function summonJev(wake = false): void {
  const win = jevOverlay ?? createJevOverlay();
  if (win.isVisible()) {
    win.hide();
  } else {
    win.show();
    win.focus();
    win.webContents.send("jev-summon", { wake });
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
const wakePollUrl = (): string => `${getBackendUrl()}/api/v1/jev/wakeword/event`;
let wakePollTimer: NodeJS.Timeout | null = null;
/** [jev-packaging] Main-process view of the wake-word switch (tray + overlay sync). */
let wakeWordOn = false;

async function pollWakeWord(): Promise<void> {
  try {
    const res = await fetch(wakePollUrl());
    if (!res.ok) return;
    const data = (await res.json()) as { wake?: boolean };
    if (data.wake) {
      console.log("[Jev] Wake word heard — summoning");
      summonJev(true);
    }
  } catch {
    // Backend not up (yet) — stay quiet and keep polling.
  }
}

function setWakeWordPolling(enabled: boolean): void {
  if (wakePollTimer) {
    clearInterval(wakePollTimer);
    wakePollTimer = null;
  }
  if (enabled) {
    console.log("[Jev] Wake-word polling started");
    wakePollTimer = setInterval(() => void pollWakeWord(), 500);
  } else {
    console.log("[Jev] Wake-word polling stopped");
  }
}

/**
 * [jev-packaging] Central wake-word switch: drives the backend listener
 * service, the main-process poller, the persisted setting, the overlay
 * checkbox and the tray menu from one place.
 */
async function setWakeWordEnabled(on: boolean): Promise<void> {
  wakeWordOn = on;
  setWakeWordPolling(on);
  setSetting("wakeWordEnabled", on);
  try {
    await fetch(`${getBackendUrl()}/api/v1/jev/wakeword/${on ? "enable" : "disable"}`, {
      method: "POST",
    });
  } catch {
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
  } catch (err) {
    console.error(`[Jev] backend failed to start: ${err}`);
    // startBackend already showed the error dialog.
    app.quit();
    return;
  }

  // [jev-packaging] Tray icon + start-at-login, and the wake-word tray hook.
  createTray({ onSummon: () => summonJev(false) });
  registerWakeWordControl({
    isEnabled: () => wakeWordOn,
    setEnabled: (on: boolean) => void setWakeWordEnabled(on),
  });
  applyStoredLoginSetting();
  if (getSetting<boolean>("wakeWordEnabled", false)) {
    void setWakeWordEnabled(true);
  }

  const registered = globalShortcut.register(JEV_HOTKEY, () => summonJev(false));
  if (!registered) {
    console.error(`[Jev] Failed to register global hotkey ${JEV_HOTKEY}`);
  } else {
    console.log(`[Jev] Global hotkey registered: ${JEV_HOTKEY}`);
  }

  ipcMain.on("jev-hide-overlay", () => {
    jevOverlay?.hide();
  });

  ipcMain.on("jev-wakeword-polling", (_event, enabled: boolean) => {
    void setWakeWordEnabled(enabled === true);
  });

  ipcMain.on("jev-open-external", (_event, url: string) => {
    if (typeof url === "string" && /^https?:\/\//.test(url)) {
      shell.openExternal(url);
    }
  });

  // [jev-packaging] First-run: Ollama check before showing the desktop.
  // Jev's brain is not bundled (multi-GB weights), so guide the install.
  if (await isOllamaReachable()) {
    createMainWindow();
  } else {
    console.log("[Jev] Ollama not reachable — showing first-run setup");
    showSetupWindow(path.join(__dirname, "preload.js"), () => createMainWindow());
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
  if (process.platform !== "darwin") app.quit();
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) createMainWindow();
});
