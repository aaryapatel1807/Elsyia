/**
 * Elsyia screen-aware mode — global hotkey wiring (main process).
 *
 * [elsyia-see] Press the hotkey to open the region-select overlay. The main
 * process only forwards the press; the overlay owns selection, capture
 * goes through desktopCapturer, and the backend stores it. This module is
 * intentionally self-contained so other main-process work stays
 * untouched apart from the one call site in main.ts.
 *
 * Privacy: this hotkey is the ONLY trigger for screen capture in Elsyia.
 * There is no background watching and no ambient screenshots anywhere.
 */
import { globalShortcut } from "electron";

/** Default global hotkey; override with ELSYIA_SEE_HOTKEY before launch. */
export const SEE_HOTKEY =
  process.env.ELSYIA_SEE_HOTKEY || "CommandOrControl+Shift+S";

export interface SeeHotkeyDeps {
  /** Called on every hotkey press — opens the region-select overlay. */
  onPress: () => void;
}

/** Register the screen-aware hotkey. Returns false if the OS refused it. */
export function registerSeeHotkey(deps: SeeHotkeyDeps): boolean {
  const ok = globalShortcut.register(SEE_HOTKEY, deps.onPress);
  if (ok) {
    console.log(`[Elsyia] Screen-aware hotkey registered: ${SEE_HOTKEY}`);
  } else {
    console.error(`[Elsyia] Failed to register screen-aware hotkey ${SEE_HOTKEY}`);
  }
  return ok;
}

export interface Rect {
  x: number;
  y: number;
  width: number;
  height: number;
}

/**
 * Normalize a mouse drag (start + current point, CSS px) into a rect.
 * Pure — unit-tested (see backend/tests/test_elsyia_see.py for the contract;
 * the TS implementation is exercised via the compiled smoke check).
 */
export function normalizeRect(
  start: { x: number; y: number },
  current: { x: number; y: number }
): Rect {
  return {
    x: Math.min(start.x, current.x),
    y: Math.min(start.y, current.y),
    width: Math.abs(current.x - start.x),
    height: Math.abs(current.y - start.y),
  };
}

/**
 * Convert a CSS-px selection rect to device-px crop bounds for the
 * display's scale factor, clamped to non-negative origins and a
 * minimum of 1px. Pure — unit-tested alongside normalizeRect.
 */
export function toCropBounds(rect: Rect, scale: number): Rect {
  const s = scale > 0 ? scale : 1;
  return {
    x: Math.max(0, Math.round(rect.x * s)),
    y: Math.max(0, Math.round(rect.y * s)),
    width: Math.max(1, Math.round(rect.width * s)),
    height: Math.max(1, Math.round(rect.height * s)),
  };
}
