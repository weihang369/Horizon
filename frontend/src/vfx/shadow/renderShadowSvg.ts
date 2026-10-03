// renderShadowSvg(spec) → SVG string. PURE and Node-safe (no DOM): the EE's seed build imports it.
// Geometry: viewBox 0 0 300 400 (3:4). Eyes at (132,130)/(168,130) = 32.5% from the top, mouth at (150,165).
import type { Emotion } from "../../contract/types";
import type { ShadowAccessory, ShadowHair, ShadowSpec } from "./types";

const INK = "#0B0B0F";
const PAPER = "#F5F2EA";
const ANGRY = "#FF3355";
const BLUSH = "#FF7A9A";

const HAIR: Record<ShadowHair, string> = {
  buzz: "M104,128C102,92 198,92 196,128C186,112 114,112 104,128Z",
  short: "M100,140C96,82 204,82 200,140C190,108 110,108 100,140Z",
  bob: "M96,150C88,70 212,70 204,150L210,210L182,200L182,120L118,120L118,200L90,210Z",
  shoulder: "M96,150C88,70 212,70 204,150L212,244L184,236L182,120L118,120L116,236L88,244Z",
  long: "M96,150C88,70 212,70 204,150L214,330L184,318L182,120L118,120L116,318L86,330Z",
  bun: "M100,140C96,82 204,82 200,140C190,108 110,108 100,140Z M170,72a20,20 0 1,0 -40,0a20,20 0 1,0 40,0Z",
  slicked: "M100,138C94,80 206,80 200,138C192,104 112,100 100,138Z M196,110C220,120 214,160 200,170C206,150 204,128 196,110Z",
  ponytail: "M100,140C96,82 204,82 200,140C190,108 110,108 100,140Z M196,104C228,112 232,170 214,214C216,170 210,132 196,104Z",
  twin: "M100,140C96,82 204,82 200,140C190,108 110,108 100,140Z M100,112C70,120 64,190 78,236C84,190 92,150 104,124Z M200,112C230,120 236,190 222,236C216,190 208,150 196,124Z",
};

const STREAK: Partial<Record<ShadowHair, string>> = {
  slicked: "M168,86C186,92 196,104 198,124",
  long: "M194,118C204,160 208,220 206,300",
  shoulder: "M194,118C204,150 208,200 206,236",
  bob: "M192,112C202,140 206,170 206,200",
};

function torso(shoulders = 1): string {
  const l = (x: number) => (150 - (150 - x) * shoulders).toFixed(1);
  const r = (x: number) => (150 + (x - 150) * shoulders).toFixed(1);
  return (
    `M${l(30)},400L${l(36)},306C${l(40)},276 ${l(70)},256 ${l(110)},244L131,232L169,232` +
    `L${r(190)},244C${r(230)},256 ${r(260)},276 ${r(264)},306L${r(270)},400Z`
  );
}

/** Short stable hash so several inlined SVGs never share gradient/filter ids. */
function idKey(s: string): string {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
  return (h >>> 0).toString(36);
}

function face(emotion: Emotion, variant: ShadowSpec["variant"], glow: string): string {
  const g = glow;
  const line = (d: string, c = g, w = 3) =>
    `<path d="${d}" fill="none" stroke="${c}" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round"/>`;
  if (variant === "unknown") {
    return line("M138,122C138,104 162,104 162,120C162,132 150,132 150,146", g, 5) + `<circle cx="150" cy="160" r="3.5" fill="${g}"/>`;
  }
  if (variant === "blink") return line("M125,131L139,131") + line("M161,131L175,131") + line("M143,165L157,165");
  switch (emotion) {
    case "happy":
      return (
        line("M125,133Q132,122 139,133") + line("M161,133Q168,122 175,133") + line("M139,161Q150,176 161,161") +
        sparkle(110, 112, 5, PAPER) + sparkle(194, 120, 4, PAPER)
      );
    case "sad":
      return (
        line("M125,135Q131,127 139,129") + line("M175,135Q169,127 161,129") + line("M140,170Q150,161 160,170") +
        `<path d="M128,140C124,147 124,151 128,151C132,151 132,147 128,140Z" fill="${PAPER}" fill-opacity=".85"/>`
      );
    case "angry":
      return (
        `<path d="M124,127L140,133L124,134Z" fill="${ANGRY}"/><path d="M176,127L160,133L176,134Z" fill="${ANGRY}"/>` +
        line("M120,118L142,126", ANGRY) + line("M180,118L158,126", ANGRY) +
        line("M138,168L143,163L148,168L153,163L158,168L162,164", ANGRY, 2.5)
      );
    case "surprised":
      return (
        `<circle cx="132" cy="130" r="7" fill="${g}"/><circle cx="168" cy="130" r="7" fill="${g}"/>` +
        `<circle cx="132" cy="130" r="2" fill="${INK}"/><circle cx="168" cy="130" r="2" fill="${INK}"/>` +
        `<circle cx="150" cy="168" r="6" fill="${INK}" stroke="${g}" stroke-width="3"/>`
      );
    case "thinking":
      return (
        line("M125,131L139,131") + `<path d="M161,128L175,128L175,131Q168,136 161,131Z" fill="${g}"/>` +
        line("M146,167L160,163")
      );
    case "embarrassed":
      return (
        line("M126,125L137,130L126,135") + line("M174,125L163,130L174,135") +
        line("M138,166Q141,162 144,166T150,166T156,166T162,166", g, 2.5) +
        line("M117,147L123,141M123,149L129,143M129,151L135,145", BLUSH, 2.5) +
        line("M165,145L171,151M171,143L177,149M177,141L183,147", BLUSH, 2.5)
      );
    case "neutral":
    default:
      return (
        `<ellipse cx="132" cy="130" rx="7" ry="3.5" fill="${g}"/><ellipse cx="168" cy="130" rx="7" ry="3.5" fill="${g}"/>` +
        line("M143,165L157,165", g, 2.5)
      );
  }
}

function sparkle(x: number, y: number, s: number, c: string): string {
  const k = s * 0.15;
  return `<path d="M${x},${y - s}C${x + k},${y - k} ${x + k},${y - k} ${x + s},${y}C${x + k},${y + k} ${x + k},${y + k} ${x},${y + s}C${x - k},${y + k} ${x - k},${y + k} ${x - s},${y}C${x - k},${y - k} ${x - k},${y - k} ${x},${y - s}Z" fill="${c}"/>`;
}

function accessory(a: ShadowAccessory, s: ShadowSpec): string {
  const { primary, secondary, glow } = s.colors;
  const st = (d: string, c: string, w = 2.5) =>
    `<path d="${d}" fill="none" stroke="${c}" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round"/>`;
  switch (a) {
    case "tie":
      return st("M131,240L150,264L169,240", PAPER, 2) + `<path d="M146,246L154,246L158,278L150,290L142,278Z" fill="${primary}"/>`;
    case "hairpin": {
      let petals = "";
      for (let i = 0; i < 5; i++) {
        const t = (i / 5) * Math.PI * 2 - Math.PI / 2;
        petals += `<circle cx="${(186 + Math.cos(t) * 5).toFixed(1)}" cy="${(96 + Math.sin(t) * 5).toFixed(1)}" r="4" fill="${secondary}"/>`;
      }
      return petals + `<circle cx="186" cy="96" r="2.5" fill="${primary}"/>`;
    }
    case "pencil":
      return st("M124,58L178,86", secondary, 4) + `<path d="M178,86L186,90L176,90Z" fill="${primary}"/>`;
    case "bucket_hat":
      return `<path d="M110,78L190,78L208,106L92,106Z" fill="${INK}" stroke="${glow}" stroke-width="2"/>` + st("M82,108L218,108", primary, 4);
    case "headphones":
      return st("M98,140C96,62 204,62 202,140", primary, 6) +
        `<rect x="88" y="126" width="16" height="28" rx="5" fill="${primary}"/><rect x="196" y="126" width="16" height="28" rx="5" fill="${primary}"/>`;
    case "headphones_neck":
      return st("M114,212C114,244 186,244 186,212", primary, 6) +
        `<ellipse cx="112" cy="214" rx="9" ry="12" fill="${primary}"/><ellipse cx="188" cy="214" rx="9" ry="12" fill="${primary}"/>`;
    case "stethoscope":
      return st("M124,222C108,280 136,306 150,306C164,306 192,280 176,222", secondary, 3) + `<circle cx="150" cy="312" r="6" fill="${secondary}"/>`;
    case "earrings":
      return `<circle cx="101" cy="152" r="3" fill="${secondary}"/><circle cx="199" cy="152" r="3" fill="${secondary}"/>`;
    case "scarf":
      return `<path d="M118,212Q150,234 182,212L186,234Q150,256 114,234Z" fill="${primary}"/>`;
    case "pendant":
      return st("M134,236L150,262L166,236", secondary, 1.5) + `<circle cx="150" cy="266" r="4" fill="${secondary}"/>`;
    case "ear_cuff":
      return st("M200,138Q206,146 200,154", secondary, 2.5);
  }
}

function glasses(s: ShadowSpec): string {
  const c = s.colors.primary;
  const st = (d: string, w = 2.5) => `<path d="${d}" fill="none" stroke="${c}" stroke-width="${w}" stroke-linecap="round"/>`;
  switch (s.glasses) {
    case "round":
      return `<circle cx="132" cy="130" r="11" fill="none" stroke="${c}" stroke-width="2.5"/><circle cx="168" cy="130" r="11" fill="none" stroke="${c}" stroke-width="2.5"/>` + st("M143,128L157,128");
    case "square":
      return `<rect x="120" y="122" width="24" height="16" fill="none" stroke="${c}" stroke-width="2.5"/><rect x="156" y="122" width="24" height="16" fill="none" stroke="${c}" stroke-width="2.5"/>` + st("M144,128L156,128");
    case "half_rim":
      return st("M120,123L144,123M156,123L180,123M144,126L156,126", 3);
    case "pushed_up":
      return `<rect x="122" y="86" width="22" height="12" fill="none" stroke="${c}" stroke-width="2.5"/><rect x="156" y="86" width="22" height="12" fill="none" stroke="${c}" stroke-width="2.5"/>` + st("M144,91L156,91");
    case "none":
    default:
      return "";
  }
}

/** Render a Shadow Self portrait as a standalone SVG string (≈ 3–5 KB). */
export function renderShadowSvg(spec: ShadowSpec): string {
  const { primary, glow, stage, surface } = spec.colors;
  const k = idKey(`${primary}${glow}${stage}${surface}`);
  const fig =
    `<ellipse cx="150" cy="135" rx="48" ry="58"/><rect x="131" y="180" width="38" height="60"/>` +
    `<path d="${torso(spec.shoulders)}"/><path d="${HAIR[spec.hair]}"/>`;
  const back: ShadowAccessory[] = spec.accessories.filter((a) => a === "headphones_neck" || a === "scarf");
  const front = spec.accessories.filter((a) => !back.includes(a));
  const streakPath = spec.streak ? STREAK[spec.hair] : undefined;
  const lapels = spec.lapels
    ? `<path d="M131,242L116,400M169,242L184,400" fill="none" stroke="${glow}" stroke-opacity=".35" stroke-width="2"/>`
    : "";
  const content =
    // rim (primary, offset), then a glow outline pass, then the ink fill on top
    `<g fill="${primary}" transform="translate(5,-4)">${fig}</g>` +
    `<g fill="none" stroke="${glow}" stroke-opacity=".6" stroke-width="3">${fig}</g>` +
    `<g fill="${INK}">${fig}</g>` +
    (streakPath ? `<path d="${streakPath}" fill="none" stroke="${spec.streak}" stroke-width="5" stroke-linecap="round"/>` : "") +
    lapels +
    back.map((a) => accessory(a, spec)).join("") +
    front.map((a) => accessory(a, spec)).join("") +
    glasses(spec) +
    `<g filter="url(#hzg${k})">${face(spec.emotion, spec.variant, glow)}</g>`;
  const scaled = `<g transform="matrix(1.25,0,0,1.25,-37.5,-33.75)">${content}</g>`;
  const body = spec.mirror ? `<g transform="translate(300,0) scale(-1,1)">${scaled}</g>` : scaled;
  const stripe = spec.mirror ? "0,187 300,262 300,322 0,247" : "0,262 300,187 300,247 0,322";

  return (
    `<svg xmlns="http://www.w3.org/2000/svg" id="horizon-shadow" viewBox="0 0 300 400" width="300" height="400">` +
    `<defs>` +
    `<linearGradient id="hzbg${k}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${surface}"/><stop offset="1" stop-color="${stage}"/></linearGradient>` +
    `<radialGradient id="hzhalo${k}" cx=".5" cy=".34" r=".42"><stop offset="0" stop-color="${glow}" stop-opacity=".28"/><stop offset="1" stop-color="${glow}" stop-opacity="0"/></radialGradient>` +
    `<pattern id="hzdot${k}" width="8" height="8" patternUnits="userSpaceOnUse"><circle cx="4" cy="4" r="1.6" fill="${primary}"/></pattern>` +
    `<linearGradient id="hzfade${k}" x1="0" y1="0" x2="0" y2="1"><stop offset=".25" stop-color="#000"/><stop offset="1" stop-color="#fff"/></linearGradient>` +
    `<mask id="hzm${k}"><rect width="300" height="400" fill="url(#hzfade${k})"/></mask>` +
    `<filter id="hzg${k}" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="2.5" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>` +
    `</defs>` +
    `<rect width="300" height="400" fill="url(#hzbg${k})"/>` +
    `<rect width="300" height="400" fill="url(#hzdot${k})" opacity=".16" mask="url(#hzm${k})"/>` +
    `<polygon points="${stripe}" fill="${primary}" opacity=".9"/>` +
    `<rect width="300" height="400" fill="url(#hzhalo${k})"/>` +
    body +
    `</svg>`
  );
}

/** Same SVG as a data URL (wizard-made characters, Kit Gallery). Contains the "horizon-shadow" marker. */
export function shadowDataUrl(spec: ShadowSpec): string {
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(renderShadowSvg(spec))}`;
}
