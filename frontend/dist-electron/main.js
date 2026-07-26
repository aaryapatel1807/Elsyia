/**
 * Elysia Electron main process.
 *
 * Phase 1 responsibilities only: create the floating window and load the
 * renderer. Push-to-talk (global shortcut → backend STT) is wired here in
 * Stage 3; automation/tool bridges are intentionally deferred to their
 * respective future phases (see docs/ROADMAP.md).
 */
import { app, BrowserWindow } from "electron";
import path from "node:path";
import { fileURLToPath } from "node:url";
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const isDev = !app.isPackaged;
function createWindow() {
    const win = new BrowserWindow({
        width: 1100,
        height: 750,
        minWidth: 720,
        minHeight: 480,
        backgroundColor: "#05050a",
        frame: false,
        titleBarStyle: "hidden",
        transparent: false,
        webPreferences: {
            preload: path.join(__dirname, "preload.js"),
            contextIsolation: true,
            nodeIntegration: false,
        },
    });
    if (isDev) {
        win.loadURL("http://localhost:5173");
        win.webContents.openDevTools({ mode: "detach" });
    }
    else {
        win.loadFile(path.join(__dirname, "../dist/index.html"));
    }
}
app.whenReady().then(createWindow);
app.on("window-all-closed", () => {
    if (process.platform !== "darwin")
        app.quit();
});
app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0)
        createWindow();
});
