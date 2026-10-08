import { useCallback, useEffect, useRef, useState } from "react";

/**
 * [elsyia-see] Screen-aware region select — the snipping-tool interaction.
 *
 * Fullscreen transparent window: drag a rectangle, release to capture,
 * Esc cancels (no capture happens). Visual language reuses the Elsyia
 * overlay exactly: dimmed backdrop, #4f7cff selection border (the
 * listening-orb blue), small-caps hint microcopy.
 *
 * Privacy: this window — opened only by the explicit Ctrl+Shift+S
 * hotkey — is the ONLY path that leads to a screen capture in Elsyia.
 * (window.elysia is typed once in ElsyiaOverlay.tsx.)
 */

interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

const MIN_SIZE = 8;

export default function SeeSelect() {
  const [rect, setRect] = useState<Rect | null>(null);
  const startRef = useRef<{ x: number; y: number } | null>(null);
  const draggingRef = useRef(false);

  const onMouseDown = useCallback((e: React.MouseEvent) => {
    if (e.button !== 0) return;
    draggingRef.current = true;
    startRef.current = { x: e.clientX, y: e.clientY };
    setRect({ x: e.clientX, y: e.clientY, w: 0, h: 0 });
  }, []);

  const onMouseMove = useCallback((e: React.MouseEvent) => {
    if (!draggingRef.current || !startRef.current) return;
    const s = startRef.current;
    setRect({
      x: Math.min(s.x, e.clientX),
      y: Math.min(s.y, e.clientY),
      w: Math.abs(e.clientX - s.x),
      h: Math.abs(e.clientY - s.y),
    });
  }, []);

  const onMouseUp = useCallback(() => {
    if (!draggingRef.current) return;
    draggingRef.current = false;
    const r = rect;
    setRect(null);
    if (r && r.w >= MIN_SIZE && r.h >= MIN_SIZE) {
      window.elysia?.selectSeeRegion?.({ x: r.x, y: r.y, width: r.w, height: r.h });
    }
    // Below the minimum size: treat as a cancelled drag, stay open.
  }, [rect]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.code === "Escape") {
        e.preventDefault();
        window.elysia?.cancelSeeSelect?.();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div
      onMouseDown={onMouseDown}
      onMouseMove={onMouseMove}
      onMouseUp={onMouseUp}
      style={{
        width: "100vw",
        height: "100vh",
        background: "rgba(8, 8, 14, 0.45)",
        cursor: "crosshair",
        position: "relative",
        overflow: "hidden",
        userSelect: "none",
      }}
    >
      <div
        style={{
          position: "absolute",
          top: 24,
          left: 0,
          right: 0,
          textAlign: "center",
          fontSize: 12,
          letterSpacing: "0.22em",
          textTransform: "uppercase",
          color: "#8b8ba3",
          fontFamily: "ui-sans-serif, system-ui, sans-serif",
          pointerEvents: "none",
        }}
      >
        Drag to select · Esc to cancel
      </div>
      <div
        style={{
          position: "absolute",
          bottom: 24,
          left: 0,
          right: 0,
          textAlign: "center",
          fontSize: 11,
          letterSpacing: "0.06em",
          color: "#6d6d85",
          fontFamily: "ui-sans-serif, system-ui, sans-serif",
          pointerEvents: "none",
        }}
      >
        Elsyia only looks when you ask.
      </div>
      {rect && rect.w > 0 && rect.h > 0 && (
        <div
          style={{
            position: "absolute",
            left: rect.x,
            top: rect.y,
            width: rect.w,
            height: rect.h,
            border: "2px solid #4f7cff",
            boxShadow: "0 0 24px rgba(90,140,255,0.45)",
            background: "rgba(79,124,255,0.06)",
            pointerEvents: "none",
          }}
        />
      )}
    </div>
  );
}
