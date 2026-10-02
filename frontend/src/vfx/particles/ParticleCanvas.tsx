// <ParticleCanvas> — a pointer-events:none canvas that owns one ParticleField. Owner: VMD.
// The field is handed to the parent through `onField` (refs only; particles never re-render React).
import { useEffect, useLayoutEffect, useRef, type CSSProperties } from "react";
import { ParticleField } from "./engine";

export interface ParticleCanvasProps {
  onField: (field: ParticleField | null) => void;
  className?: string;
  style?: CSSProperties;
}

export function ParticleCanvas({ onField, className, style }: ParticleCanvasProps) {
  const ref = useRef<HTMLCanvasElement>(null);
  const cb = useRef(onField);
  useLayoutEffect(() => {
    cb.current = onField;
  });
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const field = new ParticleField(el);
    cb.current(field);
    const ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(() => field.resize()) : null;
    ro?.observe(el);
    return () => {
      ro?.disconnect();
      field.destroy();
      cb.current(null);
    };
  }, []);
  return (
    <canvas
      ref={ref}
      aria-hidden="true"
      className={className}
      style={{ position: "absolute", pointerEvents: "none", ...style }}
    />
  );
}
