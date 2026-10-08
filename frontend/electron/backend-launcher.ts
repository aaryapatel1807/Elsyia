/**
 * backend-launcher.ts — spawns and supervises the Elsyia backend (FastAPI).
 *
 * Production (packaged app): the PyInstaller-frozen `elsyia-backend` binary
 * ships inside <resources>/backend/ and is spawned on app start with:
 *   - a free loopback port (passed as PORT)
 *   - ELSYIA_USER_DATA pointing at the user's app-data dir (all SQLite DBs,
 *     logs and downloaded models land there, never in the bundle)
 *   - a per-install SECRET_KEY generated once and stored in userData
 * stdout/stderr are piped to <userData>/logs/backend.log. The process is
 * killed when the app quits.
 *
 * Development: untouched — the developer runs uvicorn themselves
 * (default http://127.0.0.1:8000, or ELSYIA_DEV_PORT); we only resolve the
 * URL and expose it to the renderer via process.env.ELSYIA_BACKEND_URL.
 */
import { app, dialog } from "electron";
import { spawn, type ChildProcess } from "node:child_process";
import crypto from "node:crypto";
import fs from "node:fs";
import net from "node:net";
import path from "node:path";

const isDev = !app.isPackaged;
const HEALTH_TIMEOUT_MS = 90_000;
const HEALTH_POLL_MS = 500;

let backendProc: ChildProcess | null = null;
let backendUrl = "";

/** The backend base URL, e.g. http://127.0.0.1:51234 */
export function getBackendUrl(): string {
  return backendUrl;
}

/** Where the frozen backend binary lives in the packaged app. */
export function backendBinaryPath(): string {
  const exe = process.platform === "win32" ? "elsyia-backend.exe" : "elsyia-backend";
  return path.join(process.resourcesPath, "backend", exe);
}

/** Where the openWakeWord model ships in the packaged app. */
export function wakewordModelDir(): string {
  return path.join(process.resourcesPath, "backend", "wakeword");
}

function findFreePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const addr = server.address();
      const port = typeof addr === "object" && addr ? addr.port : 8000;
      server.close(() => resolve(port));
    });
  });
}

/** Per-install secret, generated once and kept in the user-data dir. */
function ensureSecret(): string {
  const file = path.join(app.getPath("userData"), "backend-secret.key");
  try {
    if (fs.existsSync(file)) {
      const existing = fs.readFileSync(file, "utf8").trim();
      if (existing) return existing;
    }
  } catch {
    /* fall through and generate */
  }
  const secret = crypto.randomBytes(32).toString("hex");
  try {
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, secret, { mode: 0o600 });
  } catch {
    /* non-fatal: fall back to the in-memory secret */
  }
  return secret;
}

async function waitForHealth(url: string, timeoutMs: number): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  let lastError = "";
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`${url}/health`);
      if (res.ok) return;
      lastError = `HTTP ${res.status}`;
    } catch (err) {
      lastError = err instanceof Error ? err.message : String(err);
    }
    await new Promise((r) => setTimeout(r, HEALTH_POLL_MS));
  }
  throw new Error(`backend did not become healthy in ${timeoutMs / 1000}s (last: ${lastError})`);
}

function tailLog(file: string, lines: number): string {
  try {
    const content = fs.readFileSync(file, "utf8");
    return content.split("\n").slice(-lines).join("\n");
  } catch {
    return "(no log output captured)";
  }
}

/**
 * Start the backend (production) or resolve the dev URL.
 * Resolves to the backend base URL and sets process.env.ELSYIA_BACKEND_URL
 * BEFORE any window is created, so the preload bridge can expose it.
 */
export async function startBackend(): Promise<string> {
  if (isDev) {
    const port = Number.parseInt(process.env.ELSYIA_DEV_PORT ?? "8000", 10) || 8000;
    backendUrl = `http://127.0.0.1:${port}`;
    process.env.ELSYIA_BACKEND_URL = backendUrl;
    console.log(`[Elsyia] dev mode — expecting backend at ${backendUrl} (start it with uvicorn)`);
    return backendUrl;
  }

  const port = await findFreePort();
  backendUrl = `http://127.0.0.1:${port}`;
  process.env.ELSYIA_BACKEND_URL = backendUrl;

  const userData = app.getPath("userData");
  const logsDir = path.join(userData, "logs");
  fs.mkdirSync(logsDir, { recursive: true });
  const logFile = path.join(logsDir, "backend.log");

  const bin = backendBinaryPath();
  if (!fs.existsSync(bin)) {
    throw new Error(
      `Backend binary not found at ${bin}. The installer was built without 'npm run build:backend'.`,
    );
  }

  console.log(`[Elsyia] spawning backend: ${bin} on port ${port}`);
  backendProc = spawn(bin, [], {
    env: {
      ...process.env,
      HOST: "127.0.0.1",
      PORT: String(port),
      DEBUG: "false",
      ELSYIA_USER_DATA: userData,
      SECRET_KEY: ensureSecret(),
    },
    cwd: userData,
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true,
  });

  const logStream = fs.createWriteStream(logFile, { flags: "a" });
  backendProc.stdout?.on("data", (d: Buffer) => logStream.write(`[out] ${d}`));
  backendProc.stderr?.on("data", (d: Buffer) => logStream.write(`[err] ${d}`));
  backendProc.on("error", (err) => {
    console.error(`[Elsyia] backend process error: ${err.message}`);
  });
  backendProc.on("exit", (code, signal) => {
    console.error(`[Elsyia] backend exited (code=${code}, signal=${signal})`);
    backendProc = null;
  });

  try {
    await waitForHealth(backendUrl, HEALTH_TIMEOUT_MS);
  } catch (err) {
    const excerpt = tailLog(logFile, 40);
    try {
      backendProc?.kill();
    } catch {
      /* already dead */
    }
    backendProc = null;
    dialog.showErrorBox(
      "Elsyia backend failed to start",
      `${err instanceof Error ? err.message : String(err)}\n\nLast backend log output:\n${excerpt}\n\nFull log: ${logFile}`,
    );
    throw err;
  }

  console.log(`[Elsyia] backend healthy at ${backendUrl}`);
  return backendUrl;
}

/** Kill the backend child process (called on app quit). */
export function stopBackend(): void {
  if (backendProc) {
    try {
      backendProc.kill();
    } catch {
      /* already dead */
    }
    backendProc = null;
  }
}
