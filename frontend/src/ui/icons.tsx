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
export const PlayIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base({ ...p, fill: "currentColor", stroke: "none" })}><path d="M4 2.5l9.5 5.5L4 13.5z" /></svg>
);
export const PauseIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base({ ...p, fill: "currentColor", stroke: "none" })}><path d="M3.5 2.5h3v11h-3zM9.5 2.5h3v11h-3z" /></svg>
);
export const StopIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base({ ...p, fill: "currentColor", stroke: "none" })}><path d="M3.5 3.5h9v9h-9z" /></svg>
);
export const NextIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base({ ...p, fill: "currentColor", stroke: "none" })}><path d="M2.5 2.5L10 8l-7.5 5.5zM11 2.5h2.5v11H11z" /></svg>
);
export const BackIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base(p)}><path d="M10 3L5 8l5 5" /></svg>
);
export const ChevronRightIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base(p)}><path d="M6 3l5 5-5 5" /></svg>
);
export const PlusIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base(p)}><path d="M8 2.5v11M2.5 8h11" /></svg>
);
export const MoreIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base({ ...p, fill: "currentColor", stroke: "none" })}><circle cx="3" cy="8" r="1.5" /><circle cx="8" cy="8" r="1.5" /><circle cx="13" cy="8" r="1.5" /></svg>
);
export const GearIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base(p)}><circle cx="8" cy="8" r="2.3" /><path d="M8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2M3.4 3.4l1.4 1.4M11.2 11.2l1.4 1.4M3.4 12.6l1.4-1.4M11.2 4.8l1.4-1.4" /></svg>
);
export const MusicIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base(p)}><path d="M6 12V3l7-1.5V10.5" /><circle cx="4.3" cy="12" r="1.8" /><circle cx="11.3" cy="10.5" r="1.8" /></svg>
);
export const SearchIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base(p)}><circle cx="7" cy="7" r="4.5" /><path d="M10.5 10.5L14 14" /></svg>
);
export const SendIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base(p)}><path d="M2 8h11M9 4l4 4-4 4" /></svg>
);
export const InfoIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base(p)}><circle cx="8" cy="8" r="6.3" /><path d="M8 7.2v4M8 4.6v.1" /></svg>
);
export const MuteIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base(p)}><path d="M2.5 6h2.5L8.5 3v10L5 10H2.5z" /><path d="M11 6l3.5 4M14.5 6L11 10" /></svg>
);
export const VolumeIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base(p)}><path d="M2.5 6h2.5L8.5 3v10L5 10H2.5z" /><path d="M11 5.5a3.5 3.5 0 0 1 0 5M12.8 3.8a6 6 0 0 1 0 8.4" /></svg>
);
