#!/usr/bin/env node
/**
 * build-backend.js — freeze the FastAPI backend with PyInstaller and stage
 * the binary into frontend/resources/backend/ for electron-builder.
 *
 * Run from frontend/:   npm run build:backend
 *
 * PyInstaller cannot cross-compile: the binary always targets the machine
 * it is built on. Build on Windows for the .exe, on macOS for the .dmg,
 * on Linux for the AppImage. (The GitHub release workflow does exactly
 * this on hosted runners.)
 */
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const frontendDir = path.resolve(__dirname, "..");
const backendDir = path.resolve(frontendDir, "..", "backend");

function findPython() {
  const candidates = [
    path.join(backendDir, ".venv", "Scripts", "python.exe"), // Windows venv
    path.join(backendDir, ".venv", "bin", "python"), // macOS/Linux venv
    process.platform === "win32" ? "python" : "python3",
  ];
  for (const c of candidates) {
    try {
      execFileSync(c, ["--version"], { stdio: "ignore" });
      return c;
    } catch {
      /* try next */
    }
  }
  throw new Error("No Python found — install Python 3.11+ and create backend/.venv (uv sync).");
}

const python = findPython();
console.log(`[build:backend] python: ${python}`);
try {
  execFileSync(python, ["-c", "import PyInstaller"], { stdio: "ignore" });
} catch {
  console.log("[build:backend] installing pyinstaller into the backend venv…");
  execFileSync(python, ["-m", "pip", "install", "pyinstaller"], { stdio: "inherit" });
}

console.log("[build:backend] freezing backend (this takes a few minutes)…");
execFileSync(python, ["-m", "PyInstaller", "--noconfirm", "--clean", "jev-backend.spec"], {
  cwd: backendDir,
  stdio: "inherit",
});

const exeName = "jev-backend" + (process.platform === "win32" ? ".exe" : "");
const src = path.join(backendDir, "dist", exeName);
if (!fs.existsSync(src)) {
  throw new Error(`PyInstaller did not produce ${src}`);
}
const destDir = path.join(frontendDir, "resources", "backend");
fs.mkdirSync(destDir, { recursive: true });
fs.copyFileSync(src, path.join(destDir, exeName));
try {
  fs.chmodSync(path.join(destDir, exeName), 0o755);
} catch {
  /* Windows has no POSIX modes */
}
console.log(`[build:backend] staged ${exeName} -> ${destDir}`);
