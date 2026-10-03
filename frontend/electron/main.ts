/**
 * Elysia Electron main process.
 *
 * - Main window: the full Elysia desktop.
 * - Jev overlay: a small always-on-top summon window, toggled from
 *   anywhere with the global hotkey Ctrl+Shift+J (Cmd+Shift+J on macOS).
 *   The overlay runs Jev's tight voice loop (mic -> Whisper -> Ollama
 *   -> actions -> TTS) through the backend /jev endpoints.
 */
import { app, BrowserWindow, globalShortcut, ipcMain, session } from "electron";
import path from "node:path";
import { fileURLToPath } from "node:url";

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
 */
const WAKE_POLL_URL = "http://127.0.0.1:8000/api/v1/jev/wakeword/event";
let wakePollTimer: NodeJS.Timeout | null = null;

async function pollWakeWord(): Promise<void> {
  try {
    const res = await fetch(WAKE_POLL_URL);
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

app.whenReady().then(() => {
  session.defaultSession.setPermissionRequestHandler((_webContents, _permission, callback) => {
    callback(true);
  });
  session.defaultSession.setPermissionCheckHandler(() => true);

  createMainWindow();

  const registered = globalShortcut.register(JEV_HOTKEY, summonJev);
  if (!registered) {
    console.error(`[Jev] Failed to register global hotkey ${JEV_HOTKEY}`);
  } else {
    console.log(`[Jev] Global hotkey registered: ${JEV_HOTKEY}`);
  }

  ipcMain.on("jev-hide-overlay", () => {
    jevOverlay?.hide();
  });

  ipcMain.on("jev-wakeword-polling", (_event, enabled: boolean) => {
    setWakeWordPolling(enabled === true);
  });
});

app.on("will-quit", () => {
  if (wakePollTimer) {
    clearInterval(wakePollTimer);
    wakePollTimer = null;
  }
  globalShortcut.unregisterAll();
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) createMainWindow();
});
