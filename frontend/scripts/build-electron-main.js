#!/usr/bin/env node
/**
 * build-electron-main.js — compile the Electron main-process sources.
 *
 * main.ts (and its modules) compile as ES modules, but the preload script
 * MUST be CommonJS: Electron 32 does not execute ESM preload scripts, so
 * an ESM preload silently leaves window.elysia undefined. The preload is
 * therefore compiled with tsconfig.preload.json and renamed to .cjs, which
 * Node/Electron always treat as CommonJS regardless of "type": "module".
 *
 * Usage: node scripts/build-electron-main.js [--watch]
 * (watch mode re-runs the rename after each preload rebuild)
 */
import { execFileSync, spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const frontendDir = path.resolve(__dirname, "..");
const outDir = path.join(frontendDir, "dist-electron");

function compilePreload() {
  execFileSync("npx", ["tsc", "-p", "electron/tsconfig.preload.json"], {
    cwd: frontendDir,
    stdio: "inherit",
  });
  const js = path.join(outDir, "preload.js");
  const cjs = path.join(outDir, "preload.cjs");
  if (fs.existsSync(js)) {
    fs.renameSync(js, cjs);
    console.log("[build:electron-main] preload.cjs written");
  }
}

if (process.argv.includes("--watch")) {
  // One-shot main build, then watch both configs; rename preload on rebuild.
  execFileSync("npx", ["tsc", "-p", "electron/tsconfig.json"], { cwd: frontendDir, stdio: "inherit" });
  compilePreload();
  const w1 = spawn("npx", ["tsc", "-p", "electron/tsconfig.json", "--watch"], { cwd: frontendDir, stdio: "inherit" });
  const w2 = spawn("npx", ["tsc", "-p", "electron/tsconfig.preload.json", "--watch", "--preserveWatchOutput"], {
    cwd: frontendDir,
    stdio: "pipe",
  });
  w2.stdout.on("data", (d) => {
    process.stdout.write(d);
    if (d.toString().includes("Found 0 errors")) compilePreload();
  });
  w2.stderr.pipe(process.stderr);
  const stop = () => { w1.kill(); w2.kill(); };
  process.on("SIGINT", stop);
  process.on("SIGTERM", stop);
} else {
  execFileSync("npx", ["tsc", "-p", "electron/tsconfig.json"], { cwd: frontendDir, stdio: "inherit" });
  compilePreload();
}
