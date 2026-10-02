// Minimal inline SVG icons used by primitives (stroke = currentColor).
import type { SVGProps } from "react";

const base = (p: SVGProps<SVGSVGElement>) => ({
  width: 16, height: 16, viewBox: "0 0 16 16", fill: "none", stroke: "currentColor",
  strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true, ...p,
});

export const KeyIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base(p)}><circle cx="5" cy="8" r="3" /><path d="M8 8h7M12.5 8v2.5M15 8v2" /></svg>
);
export const RegenIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base(p)}><path d="M13.5 8A5.5 5.5 0 1 1 11.8 4" /><path d="M13.5 2.5V5H11" /></svg>
);
export const CloseIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base(p)}><path d="M3.5 3.5l9 9M12.5 3.5l-9 9" /></svg>
);
export const ChevronDownIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base(p)}><path d="M3.5 6l4.5 4.5L12.5 6" /></svg>
);
export const BoltIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base({ ...p, fill: "currentColor", stroke: "none" })}><path d="M9.5 1L3 9.2h4.2L6.3 15 13 6.6H8.7z" /></svg>
);
export const CheckIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base(p)}><path d="M3 8.5l3.2 3L13 4.5" /></svg>
);
export const WarnIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base(p)}><path d="M8 1.8L15 14H1z" /><path d="M8 6.2v3.6M8 11.9v.1" /></svg>
);
