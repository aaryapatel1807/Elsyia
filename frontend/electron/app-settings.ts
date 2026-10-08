/**
 * app-settings.ts — tiny JSON settings store in the user-data dir.
 * No extra dependencies; just enough for login/tray/wake-word toggles.
 */
import { app } from "electron";
import fs from "node:fs";
import path from "node:path";

function settingsFile(): string {
  return path.join(app.getPath("userData"), "elsyia-settings.json");
}

function readAll(): Record<string, unknown> {
  try {
    return JSON.parse(fs.readFileSync(settingsFile(), "utf8")) as Record<string, unknown>;
  } catch {
    return {};
  }
}

export function getSetting<T>(key: string, fallback: T): T {
  const all = readAll();
  return (all[key] as T) ?? fallback;
}

export function setSetting(key: string, value: unknown): void {
  const all = readAll();
  all[key] = value;
  try {
    fs.mkdirSync(path.dirname(settingsFile()), { recursive: true });
    fs.writeFileSync(settingsFile(), JSON.stringify(all, null, 2));
  } catch (err) {
    console.error(`[Elsyia] failed to persist setting ${key}:`, err);
  }
}
