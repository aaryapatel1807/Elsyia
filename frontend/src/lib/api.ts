/**
 * api.ts — backend URL resolution for the renderer.
 *
 * In the packaged app the Electron main process spawns the backend on a
 * free loopback port and exposes it through the preload bridge
 * (window.elysia.backendUrl()). In dev it falls back to the local
 * uvicorn default. Always use apiBase() instead of a hardcoded port.
 */

// NOTE: the full window.elysia bridge shape is declared in
// components/ElsyiaOverlay.tsx; this file uses a local structural type so the
// two global augmentations can never clash.
interface ElysiaBridge {
  backendUrl?: () => string;
}

/** Base URL of the backend, e.g. http://127.0.0.1:51234 */
export function backendUrl(): string {
  try {
    const bridge = (window as unknown as { elysia?: ElysiaBridge }).elysia;
    const fromBridge = bridge?.backendUrl?.();
    if (typeof fromBridge === "string" && fromBridge.length > 0) {
      return fromBridge.replace(/\/+$/, "");
    }
  } catch {
    /* preload bridge unavailable (plain browser dev) — fall through */
  }
  return "http://127.0.0.1:8000";
}

/** API root, e.g. http://127.0.0.1:51234/api/v1 */
export function apiBase(): string {
  return `${backendUrl()}/api/v1`;
}
