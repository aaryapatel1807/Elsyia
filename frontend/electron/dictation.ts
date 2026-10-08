/**
 * Elsyia dictation mode — global hotkey wiring (main process).
 *
 * [elsyia-dictation] Press the hotkey once to start recording, press again to
 * stop and process. The overlay owns the toggle state (recording -> preview
 * -> typing); the main process only forwards the key press, exactly like the
 * Ctrl+Shift+J summon. This module is intentionally self-contained so the
 * packaging work in main.ts stays untouched apart from the one call site.
 */
import { globalShortcut } from "electron";

/** Default global hotkey; override with ELSYIA_DICTATION_HOTKEY before launch. */
export const DICTATION_HOTKEY =
  process.env.ELSYIA_DICTATION_HOTKEY || "CommandOrControl+Shift+D";

export interface DictationHotkeyDeps {
  /** Called on every hotkey press — the overlay toggles record/stop/type. */
  onToggle: () => void;
}

/** Register the dictation hotkey. Returns false if the OS refused it. */
export function registerDictationHotkey(deps: DictationHotkeyDeps): boolean {
  const ok = globalShortcut.register(DICTATION_HOTKEY, deps.onToggle);
  if (ok) {
    console.log(`[Elsyia] Dictation hotkey registered: ${DICTATION_HOTKEY}`);
  } else {
    console.error(`[Elsyia] Failed to register dictation hotkey ${DICTATION_HOTKEY}`);
  }
  return ok;
}
