/**
 * app-settings.ts — tiny JSON settings store in the user-data dir.
 * No extra dependencies; just enough for login/tray/wake-word toggles.
 */
import { app } from "electron";
import fs from "node:fs";
import path from "node:path";
function settingsFile() {
    return path.join(app.getPath("userData"), "jev-settings.json");
}
function readAll() {
    try {
        return JSON.parse(fs.readFileSync(settingsFile(), "utf8"));
    }
    catch {
        return {};
    }
}
export function getSetting(key, fallback) {
    const all = readAll();
    return all[key] ?? fallback;
}
export function setSetting(key, value) {
    const all = readAll();
    all[key] = value;
    try {
        fs.mkdirSync(path.dirname(settingsFile()), { recursive: true });
        fs.writeFileSync(settingsFile(), JSON.stringify(all, null, 2));
    }
    catch (err) {
        console.error(`[Jev] failed to persist setting ${key}:`, err);
    }
}
