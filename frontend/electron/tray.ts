/**
 * tray.ts — system tray icon with Show/Hide, wake-word toggle, login toggle, Quit.
 *
 * The wake-word menu item is driven through registerWakeWordControl(),
 * which the wake-word module calls once its listener is wired up. Until
 * then the item is shown disabled — this keeps tray.ts independent of the
 * wake-word implementation (rebase-friendly).
 */
import { app, Menu, Tray, nativeImage } from "electron";
import path from "node:path";
import { getSetting, setSetting } from "./app-settings.js";

export interface WakeWordControl {
  isEnabled: () => boolean;
  setEnabled: (enabled: boolean) => void;
}

let wakeWordControl: WakeWordControl | null = null;

/** Called by the wake-word module once its listener is ready. */
export function registerWakeWordControl(control: WakeWordControl): void {
  wakeWordControl = control;
}

function trayIconPath(): string {
  const rel = path.join("icons", "tray.png");
  return app.isPackaged
    ? path.join(process.resourcesPath, rel)
    : path.join(__dirname, "..", "build-resources", rel);
}

export function applyStoredLoginSetting(): void {
  if (getSetting<boolean>("startAtLogin", false)) {
    app.setLoginItemSettings({ openAtLogin: true, path: process.execPath, args: [] });
  }
}

function setLoginItem(enabled: boolean): void {
  app.setLoginItemSettings({ openAtLogin: enabled, path: process.execPath, args: [] });
  setSetting("startAtLogin", enabled);
}

let tray: Tray | null = null;
let rebuildMenu: (() => void) | null = null;

/** Rebuild the tray menu (called when the wake-word switch changes elsewhere). */
export function refreshTrayMenu(): void {
  rebuildMenu?.();
}

export function createTray(opts: { onSummon: () => void }): Tray {
  tray = new Tray(nativeImage.createFromPath(trayIconPath()));
  tray.setToolTip("Elsyia — your voice assistant");

  const rebuild = (): void => {
    const wakeEnabled = wakeWordControl
      ? wakeWordControl.isEnabled()
      : getSetting<boolean>("wakeWordEnabled", false);
    const loginEnabled = getSetting<boolean>("startAtLogin", false);
    const menu = Menu.buildFromTemplate([
      { label: "Show / hide Elsyia", click: opts.onSummon },
      { type: "separator" },
      {
        label: "Wake word listening",
        type: "checkbox",
        checked: wakeEnabled,
        enabled: wakeWordControl !== null,
        toolTip: wakeWordControl
          ? "Toggle the always-on wake-word listener"
          : "Wake-word module not loaded yet",
        click: (item) => {
          wakeWordControl?.setEnabled(item.checked);
          setSetting("wakeWordEnabled", item.checked);
          rebuild();
        },
      },
      {
        label: "Start at login",
        type: "checkbox",
        checked: loginEnabled,
        click: (item) => {
          setLoginItem(item.checked);
          rebuild();
        },
      },
      { type: "separator" },
      { label: "Quit Elsyia", click: () => app.quit() },
    ]);
    tray?.setContextMenu(menu);
  };

  tray.on("click", opts.onSummon);
  rebuildMenu = rebuild;
  rebuild();
  return tray;
}
