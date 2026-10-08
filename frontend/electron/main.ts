/**
 * Elysia Electron main process.
 *
 * - Main window: the full Elysia desktop.
 * - Elsyia overlay: a small always-on-top summon window, toggled from
 *   anywhere with the global hotkey Ctrl+Shift+J (Cmd+Shift+J on macOS).
 *   The overlay runs Elsyia's tight voice loop (mic -> Whisper -> Ollama
 *   -> actions -> TTS) through the backend /elsyia endpoints.
 */
import { app, BrowserWindow, desktopCapturer, dialog, globalShortcut, ipcMain, screen, session, shell } from "electron";
import path from "node:path";
import { fileURLToPath } from "node:url";
// [elsyia-packaging] Desktop-app modules: backend supervisor, tray, first-run.
import { getBackendUrl, startBackend, stopBackend } from "./backend-launcher.js";
import { getSetting, setSetting } from "./app-settings.js";
import { applyStoredLoginSetting, createTray, refreshTrayMenu, registerWakeWordControl } from "./tray.js";
import { isOllamaReachable, showSetupWindow } from "./first-run.js";
// [elsyia-dictation] Global hotkey module (say it, it types). Additive — the
// overlay owns the record/stop/type toggle state; main only forwards presses.
import { registerDictationHotkey } from "./dictation.js";
// [elsyia-see] Screen-aware hotkey module (circle anything, then just ask).
// Additive — main only forwards the press and performs the explicit
// region capture; the overlay owns the Q&A UI.
import { registerSeeHotkey, normalizeRect, toCropBounds } from "./see.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const isDev = !app.isPackaged;
const ELSYIA_HOTKEY = "CommandOrControl+Shift+J";

let mainWindow: BrowserWindow | null = null;
let elsyiaOverlay: BrowserWindow | null = null;

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
      preload: path.join(__dirname, "preload.cjs"),
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

function createElsyiaOverlay(): BrowserWindow {
  elsyiaOverlay = new BrowserWindow({
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
    elsyiaOverlay.loadURL("http://localhost:5173/?overlay=elsyia");
  } else {
    elsyiaOverlay.loadFile(path.join(__dirname, "../dist/index.html"), {
      query: { overlay: "elsyia" },
    });
  }
  elsyiaOverlay.on("closed", () => {
    elsyiaOverlay = null;
  });
  return elsyiaOverlay;
}

/** Toggle the Elsyia overlay from anywhere in the OS. */
function summonElsyia(wake = false): void {
  const win = elsyiaOverlay ?? createElsyiaOverlay();
  if (win.isVisible()) {
    win.hide();
  } else {
    win.show();
    win.focus();
    win.webContents.send("elsyia-summon", { wake });
  }
}

/**
 * [elsyia-see] Screen-aware region select.
 *
 * A fullscreen transparent window where the user drags a rectangle
 * (Esc cancels). The selection is captured via desktopCapturer, POSTed
 * to the backend as the current explicit capture, and the Elsyia overlay
 * opens in see-mode. THIS IS THE ONLY SCREEN-CAPTURE PATH IN ELSYIA —
 * there is no background watching and no ambient screenshots anywhere.
 */
let seeSelectWindow: BrowserWindow | null = null;

function openSeeSelect(): void {
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
  } else {
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

async function handleSeeRegion(rect: {
  x: number;
  y: number;
  width: number;
  height: number;
}): Promise<void> {
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
    const source =
      sources.find((s) => s.display_id === String(display.id)) ?? sources[0];
    if (!source) throw new Error("No screen source available.");
    const cropped = source.thumbnail.crop(
      toCropBounds(
        normalizeRect(
          { x: rect.x, y: rect.y },
          { x: rect.x + rect.width, y: rect.y + rect.height }
        ),
        scale
      )
    );
    const png = cropped.toPNG();
    // Store as the current explicit capture (the only write path).
    const form = new FormData();
    form.append("file", new Blob([new Uint8Array(png)]), "capture.png");
    const res = await fetch(`${getBackendUrl()}/api/v1/elsyia/see/capture`, {
      method: "POST",
      body: form,
    });
    if (!res.ok) throw new Error(`Capture upload failed: ${res.status}`);
    // Summon the overlay in see-mode with a thumbnail of the region.
    const overlay = elsyiaOverlay ?? createElsyiaOverlay();
    if (!overlay.isVisible()) overlay.show();
    overlay.focus();
    overlay.webContents.send("elsyia-summon", {
      wake: false,
      see: true,
      thumbnail: `data:image/png;base64,${png.toString("base64")}`,
    });
  } catch (err) {
    console.error("[Elsyia] Screen capture failed:", err);
    dialog.showErrorBox(
      "Elsyia — screen capture failed",
      err instanceof Error ? err.message : String(err)
    );
  }
}

/**
 * Wake-word polling: while the listener toggle is on, ask the backend
 * twice a second whether the wake phrase was heard. A hit summons Elsyia
 * exactly like the global hotkey, flagged as a hands-free wake.
 *
 * [elsyia-packaging] The backend URL is dynamic in the packaged app (the
 * launcher picks a free loopback port), so it is resolved per poll.
 */
const wakePollUrl = (): string => `${getBackendUrl()}/api/v1/elsyia/wakeword/event`;
let wakePollTimer: NodeJS.Timeout | null = null;
/** [elsyia-packaging] Main-process view of the wake-word switch (tray + overlay sync). */
let wakeWordOn = false;

async function pollWakeWord(): Promise<void> {
  try {
    const res = await fetch(wakePollUrl());
    if (!res.ok) return;
    const data = (await res.json()) as { wake?: boolean };
    if (data.wake) {
      console.log("[Elsyia] Wake word heard — summoning");
      summonElsyia(true);
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
    console.log("[Elsyia] Wake-word polling started");
    wakePollTimer = setInterval(() => void pollWakeWord(), 500);
  } else {
    console.log("[Elsyia] Wake-word polling stopped");
  }
}

/**
 * [elsyia-packaging] Central wake-word switch: drives the backend listener
 * service, the main-process poller, the persisted setting, the overlay
 * checkbox and the tray menu from one place.
 */
async function setWakeWordEnabled(on: boolean): Promise<void> {
  wakeWordOn = on;
  setWakeWordPolling(on);
  setSetting("wakeWordEnabled", on);
  try {
    await fetch(`${getBackendUrl()}/api/v1/elsyia/wakeword/${on ? "enable" : "disable"}`, {
      method: "POST",
    });
  } catch {
    // Backend not up yet — the overlay retries on its next toggle/status fetch.
  }
  for (const win of BrowserWindow.getAllWindows()) {
    win.webContents.send("elsyia-wakeword-state", on);
  }
  refreshTrayMenu();
}

app.whenReady().then(async () => {
  session.defaultSession.setPermissionRequestHandler((_webContents, _permission, callback) => {
    callback(true);
  });
  session.defaultSession.setPermissionCheckHandler(() => true);

  // [elsyia-packaging] Boot the backend first; a real error dialog, never a blank screen.
  try {
    const url = await startBackend();
    console.log(`[Elsyia] backend ready at ${url}`);
  } catch (err) {
    console.error(`[Elsyia] backend failed to start: ${err}`);
    // startBackend already showed the error dialog.
    app.quit();
    return;
  }

  // [elsyia-packaging] Tray icon + start-at-login, and the wake-word tray hook.
  createTray({ onSummon: () => summonElsyia(false) });
  registerWakeWordControl({
    isEnabled: () => wakeWordOn,
    setEnabled: (on: boolean) => void setWakeWordEnabled(on),
  });
  applyStoredLoginSetting();
  if (getSetting<boolean>("wakeWordEnabled", false)) {
    void setWakeWordEnabled(true);
  }

  const registered = globalShortcut.register(ELSYIA_HOTKEY, () => summonElsyia(false));
  if (!registered) {
    console.error(`[Elsyia] Failed to register global hotkey ${ELSYIA_HOTKEY}`);
  } else {
    console.log(`[Elsyia] Global hotkey registered: ${ELSYIA_HOTKEY}`);
  }

  // [elsyia-dictation] Say-it-it-types hotkey (default Ctrl+Shift+D, override
  // with ELSYIA_DICTATION_HOTKEY). Forwards to the overlay, which toggles
  // recording -> stop/process -> preview -> type into the focused app.
  registerDictationHotkey({
    onToggle: () => {
      const win = elsyiaOverlay ?? createElsyiaOverlay();
      if (!win.isVisible()) win.show();
      win.webContents.send("elsyia-summon", { wake: false, dictate: true });
    },
  });

  // [elsyia-see] Screen-aware hotkey (default Ctrl+Shift+S, override with
  // ELSYIA_SEE_HOTKEY). Opens the region-select overlay — the ONLY trigger
  // for screen capture. Elsyia never screenshots in the background.
  registerSeeHotkey({ onPress: () => openSeeSelect() });

  ipcMain.on("elsyia-see-region", (_event, rect) => {
    void handleSeeRegion(rect);
  });

  ipcMain.on("elsyia-see-cancel", () => {
    seeSelectWindow?.close();
  });

  ipcMain.on("elsyia-hide-overlay", () => {
    elsyiaOverlay?.hide();
  });

  ipcMain.on("elsyia-wakeword-polling", (_event, enabled: boolean) => {
    void setWakeWordEnabled(enabled === true);
  });

  ipcMain.on("elsyia-open-external", (_event, url: string) => {
    if (typeof url === "string" && /^https?:\/\//.test(url)) {
      shell.openExternal(url);
    }
  });

  // [elsyia-packaging] First-run: Ollama check before showing the desktop.
  // Elsyia's brain is not bundled (multi-GB weights), so guide the install.
  if (await isOllamaReachable()) {
    createMainWindow();
  } else {
    console.log("[Elsyia] Ollama not reachable — showing first-run setup");
    showSetupWindow(path.join(__dirname, "preload.cjs"), () => createMainWindow());
  }
});

app.on("will-quit", () => {
  if (wakePollTimer) {
    clearInterval(wakePollTimer);
    wakePollTimer = null;
  }
  stopBackend(); // [elsyia-packaging] kill the backend child process
  globalShortcut.unregisterAll();
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) createMainWindow();
});
