// resolveAudio(url) → AudioBuffer (spec §3.6). Owner: VMD. Browser only.
// Swapping procedural placeholders for real audio is a URL change only (R11):
//   *.proc.json                → fetch the spec, renderTheme(spec)
//   placeholder:sfx/<id>       → built-in SFX recipe
//   placeholder:system/<kind>  → built-in system track (main_theme | arena | ambient_bed)
//   anything else              → fetch + decodeAudioData
// Results are cached per URL (in-flight promises are shared); failures are evicted so a retry can work.
import { renderSfx, isSfxId } from "./synth/sfx";
import { isThemeProcSpec } from "./synth/spec";
import { renderTheme } from "./synth/renderTheme";
import { isSystemTrackKind, renderSystemTrack } from "./synth/system";

const cache = new Map<string, Promise<AudioBuffer>>();
let decoder: BaseAudioContext | null = null;

function decodeCtx(): BaseAudioContext {
  // An OfflineAudioContext can decode without a user gesture and never produces sound.
  decoder ??= new OfflineAudioContext(2, 1, 48000);
  return decoder;
}

/** True for URLs rendered procedurally (the mini-player shows `· SKETCH`). */
export function isProceduralAudio(url: string | null | undefined): boolean {
  if (!url) return false;
  return url.startsWith("placeholder:") || /\.proc\.json(\?|#|$)/.test(url);
}

async function load(url: string): Promise<AudioBuffer> {
  if (url.startsWith("placeholder:sfx/")) {
    const id = url.slice("placeholder:sfx/".length);
    if (!isSfxId(id)) throw new Error(`Unknown placeholder SFX: ${id}`);
    return renderSfx(id);
  }
  if (url.startsWith("placeholder:system/")) {
    const kind = url.slice("placeholder:system/".length);
    if (!isSystemTrackKind(kind)) throw new Error(`Unknown placeholder system track: ${kind}`);
    return renderSystemTrack(kind);
  }
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Audio fetch failed (${res.status}): ${url}`);
  if (/\.proc\.json(\?|#|$)/.test(url)) {
    const spec: unknown = await res.json();
    if (!isThemeProcSpec(spec)) throw new Error(`Not a horizon.theme spec: ${url}`);
    return renderTheme(spec);
  }
  return decodeCtx().decodeAudioData(await res.arrayBuffer());
}

export function resolveAudio(url: string): Promise<AudioBuffer> {
  let p = cache.get(url);
  if (!p) {
    p = load(url);
    cache.set(url, p);
    p.catch(() => {
      if (cache.get(url) === p) cache.delete(url);
    });
  }
  return p;
}

/** Warm the cache (e.g. a session's themes on open). Never rejects. */
export function preloadAudio(urls: (string | null | undefined)[]): Promise<void> {
  return Promise.all(urls.filter((u): u is string => !!u).map((u) => resolveAudio(u).catch(() => undefined))).then(() => undefined);
}

export function clearAudioCache(url?: string): void {
  if (url) cache.delete(url);
  else cache.clear();
}
