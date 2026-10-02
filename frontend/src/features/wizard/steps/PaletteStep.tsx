// S05f PALETTE (CHR-09, D-50): the AI pick is pre-set as the provisional palette; all 12 fixed palettes as skewed
// swatch cards. Hover = instant 120 ms-debounced swap on the app root (no flood); click = select + one Palette Flood
// (R10, NFR-16). Sharing a palette within the world shows a soft warning. Owner: Builder B.
import { useEffect, useRef, useState } from "react";
import { audio } from "@/audio/engine";
import { reportError } from "@/app/errors";
import { client } from "@/client";
import { useCharacters } from "@/client/hooks";
import { EnergyBar, NamePlate } from "@/character";
import { PALETTES, PaletteScope, getPalette, setAppPalette } from "@/theme";
import { Button, Swatch, Tape } from "@/ui";
import { ActionBar } from "../ActionBar";
import { useWizard } from "../context";
import { stepIndex } from "../gates";
import s from "./steps.module.css";

/** The AI's pick per character, remembered the first time the PALETTE step sees a not-yet-confirmed draft. */
const aiPickMemory = new Map<string, string>();

export function PaletteStep() {
  const { character: c, worldId, goStep, work, edit } = useWizard();
  const roster = useCharacters(worldId).data ?? [];
  const [hover, setHover] = useState<string | null>(null);
  const timer = useRef<number>(0);
  const selected = c?.paletteId ?? null;

  if (c && !aiPickMemory.has(c.id) && !edit && stepIndex(c.creationStep) <= stepIndex("palette")) aiPickMemory.set(c.id, c.paletteId);
  const aiPick = c ? aiPickMemory.get(c.id) : undefined;

  // Hover preview: instant swap, debounced, back to the selection on leave.
  useEffect(() => {
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setAppPalette(hover ?? selected), 120);
    return () => window.clearTimeout(timer.current);
  }, [hover, selected]);

  if (!c) return null;
  const shown = getPalette(hover ?? selected);
  const sharedWith = roster.filter((x) => x.id !== c.id && x.paletteId === (hover ?? selected) && x.status !== "archived");

  const pick = async (id: string, point: { x: number; y: number }, el?: Element | null) => {
    if (id === selected) return;
    let at = point;
    if (!point.x && !point.y && el) {
      const r = el.getBoundingClientRect();
      at = { x: r.left + r.width / 2, y: r.top + r.height / 2 };
    }
    window.clearTimeout(timer.current);
    setAppPalette(selected); // the flood plays only on a real change: drop the hover preview back to the old palette first
    setAppPalette(id, { flood: at });
    audio.playSfx("ui_flood");
    try {
      await client.characters.update(c.id, { paletteId: id });
    } catch (err) {
      reportError(err);
    }
  };

  const plateChar = { id: c.id, paletteId: shown.id, profile: { name: work.w.profile.name || "?", role: work.w.profile.role } };
  return (
    <>
      <section className={s.work} aria-labelledby="pal-h">
        <div className={s.stepHead}>
          <div>
            <Tape tone="ink" size="sm">Step 06 · Palette</Tape>
            <h1 id="pal-h" className={s.stepTitle}>Their colours</h1>
          </div>
          <div className={s.stepHeadRight}>
            <span className={s.microNote}>Hover to preview the whole app. Click to commit. Twelve fixed palettes; no custom colours.</span>
          </div>
        </div>
        <div className={s.palLayout}>
          <div className={s.palGrid} role="radiogroup" aria-label="Palette" onMouseLeave={() => setHover(null)}>
            {PALETTES.map((p) => (
              <Swatch
                key={p.id}
                palette={p}
                selected={p.id === selected}
                aiPick={p.id === aiPick}
                onPreview={setHover}
                onSelect={(id, pt) => void pick(id, pt, document.activeElement)}
              />
            ))}
          </div>
          <PaletteScope paletteId={shown.id} className={s.palPreview}>
            <div className={s.palPreviewHead}>
              <span className={s.palPreviewKicker}>LIVE PREVIEW</span>
              <span className={s.palPreviewName}>{shown.name}</span>
              {shown.fit && <span className={s.palPreviewFit}>{shown.fit}</span>}
            </div>
            <div className={s.palPreviewStage}>
              <NamePlate character={plateChar} size="md" />
              <EnergyBar energy={{ current: 640, max: 1000, state: "active" }} size="chat" showLabel label={plateChar.profile.name} />
              <div className={s.palBubble}><b>{work.w.profile.name || "They"}</b> {work.w.profile.greeting || "Hi! Good to finally meet you."}</div>
              <div className={s.palButtons}>
                <Button size="sm" variant="primary" tabIndex={-1}>Chat ▸</Button>
                <Tape tone="primary" size="sm">Speaking</Tape>
              </div>
            </div>
            {sharedWith.length > 0 && (
              <p className={s.palWarn} role="status">
                <Tape tone="warn" size="sm">Heads up</Tape> {sharedWith.map((x) => x.profile.name).join(", ")} already {sharedWith.length > 1 ? "wear" : "wears"} {shown.name} in this world. Allowed, just harder to tell apart.
              </p>
            )}
          </PaletteScope>
        </div>
      </section>
      <ActionBar>
        <Button variant="primary" size="lg" onClick={() => void goStep("theme")}>Next: Theme ▸</Button>
      </ActionBar>
    </>
  );
}
