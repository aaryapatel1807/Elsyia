/**
 * first-run.ts — Ollama reachability check + friendly setup screen.
 *
 * Elsyia's AI brain is Ollama, which is deliberately NOT bundled (multi-GB
 * model weights). On launch we check http://localhost:11434; if it is
 * unreachable we show a setup window guiding the user to install Ollama
 * and pull a model, instead of a mysteriously brain-dead assistant.
 */
import { BrowserWindow, ipcMain, shell } from "electron";

const OLLAMA_URL = process.env.OLLAMA_BASE_URL ?? "http://localhost:11434";
const OLLAMA_MODEL = "qwen2.5:1.5b";

export async function isOllamaReachable(): Promise<boolean> {
  try {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 4000);
    const res = await fetch(`${OLLAMA_URL}/api/tags`, { signal: ctrl.signal });
    clearTimeout(timer);
    return res.ok;
  } catch {
    return false;
  }
}

const SETUP_HTML = `<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Set up Elsyia</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, "Segoe UI", Inter, sans-serif;
         background: #0b0b16; color: #e8e8f0; padding: 40px 36px; }
  .ring { width: 64px; height: 64px; border-radius: 50%;
          border: 4px solid #6366f1; border-bottom-color: #22d3ee;
          display: flex; align-items: center; justify-content: center;
          font-size: 28px; font-weight: 700; margin-bottom: 20px; }
  h1 { font-size: 24px; margin-bottom: 8px; }
  p.sub { color: #9a9ab0; font-size: 14px; margin-bottom: 24px; line-height: 1.5; }
  .step { background: #141422; border: 1px solid #26263a; border-radius: 12px;
          padding: 16px; margin-bottom: 12px; }
  .step h2 { font-size: 14px; margin-bottom: 8px; color: #c7c7dd; }
  .step p { font-size: 13px; color: #9a9ab0; line-height: 1.55; }
  code { background: #05050c; border: 1px solid #2a2a40; border-radius: 6px;
         padding: 8px 12px; display: block; margin-top: 10px; font-size: 13px;
         color: #7df9ff; font-family: ui-monospace, monospace;
         overflow-x: auto; white-space: nowrap; }
  .row { display: flex; gap: 10px; margin-top: 10px; }
  button { cursor: pointer; border: none; border-radius: 8px; padding: 10px 18px;
           font-size: 13px; font-weight: 600; }
  .primary { background: linear-gradient(135deg, #6366f1, #22d3ee); color: #fff; flex: 1; }
  .ghost { background: #1e1e32; color: #c7c7dd; }
  a { color: #7df9ff; }
  #status { margin-top: 16px; font-size: 13px; min-height: 20px; color: #9a9ab0; }
  #status.ok { color: #4ade80; } #status.err { color: #f87171; }
</style></head><body>
  <div class="ring">J</div>
  <h1>One last step to wake Elsyia up</h1>
  <p class="sub">Elsyia's brain runs on Ollama, free and entirely on your machine.
  It is not bundled with the app because the model weights are several gigabytes.
  Two minutes, once:</p>
  <div class="step"><h2>1. Install Ollama</h2>
    <p>Download it from <a href="https://ollama.com/download" id="ollama-link">ollama.com/download</a>
    and run the installer.</p></div>
  <div class="step"><h2>2. Pull Elsyia's model</h2>
    <p>Open a terminal and run:</p>
    <code id="cmd">ollama pull ${OLLAMA_MODEL}</code>
    <div class="row"><button class="ghost" id="copy">Copy command</button></div></div>
  <div class="step"><h2>3. Check again</h2>
    <p>Once Ollama is installed and the model has downloaded:</p>
    <div class="row"><button class="primary" id="retry">Check again</button></div></div>
  <div id="status"></div>
<script>
  const api = window.elysia;
  document.getElementById('ollama-link').addEventListener('click', (e) => {
    e.preventDefault(); api.openExternal('https://ollama.com/download');
  });
  document.getElementById('copy').addEventListener('click', async () => {
    await navigator.clipboard.writeText('ollama pull ${OLLAMA_MODEL}');
    document.getElementById('status').textContent = 'Copied to clipboard.';
  });
  document.getElementById('retry').addEventListener('click', () => {
    document.getElementById('status').textContent = 'Checking for Ollama…';
    document.getElementById('status').className = '';
    api.retrySetup();
  });
  api.onSetupStatus((ok) => {
    const el = document.getElementById('status');
    if (ok) { el.textContent = 'Ollama found — starting Elsyia…'; el.className = 'ok'; }
    else { el.textContent = 'Still cannot reach Ollama. Is it installed and running?'; el.className = 'err'; }
  });
</script></body></html>`;

let setupWin: BrowserWindow | null = null;

/**
 * Show the Ollama setup window. Calls onReady() once Ollama is reachable —
 * the caller then creates the real windows.
 */
export function showSetupWindow(preloadPath: string, onReady: () => void): void {
  setupWin = new BrowserWindow({
    width: 560,
    height: 660,
    resizable: false,
    minimizable: false,
    maximizable: false,
    backgroundColor: "#0b0b16",
    webPreferences: { preload: preloadPath, contextIsolation: true, nodeIntegration: false },
  });
  setupWin.setMenuBarVisibility(false);
  setupWin.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(SETUP_HTML)}`);
  setupWin.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });
  setupWin.on("closed", () => {
    setupWin = null;
  });

  ipcMain.once("elsyia-setup-retry", async () => {
    const ok = await isOllamaReachable();
    setupWin?.webContents.send("elsyia-setup-status", ok);
    if (ok) {
      setupWin?.close();
      onReady();
    }
  });
}
