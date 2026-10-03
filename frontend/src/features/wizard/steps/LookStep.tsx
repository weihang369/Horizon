// S05c LOOK (CHR-06): Sims-style chips and swatches, AI pre-selected; selections compile into an editable summary.
// No sliders, no live morphing: only outfit colours and the palette frame preview instantly. Owner: Builder B.
import { useState } from "react";
import type { CSSProperties } from "react";
import type { Appearance } from "@/contract/types";
import { Button, ChipGroup, Tabs, Tape, TextArea } from "@/ui";
import { cx } from "@/ui/cx";
import { ActionBar } from "../ActionBar";
import { useWizard } from "../context";
import { startGeneration, useEstimate } from "../generate";
import type { LookTab, SwatchOpt } from "../options";
import {
  ACCESSORIES, AGE_BANDS, BASELINES, BUILDS, compileSummary, EYE_COLORS, EYE_SHAPES, FACE_SHAPES, FRINGES, GLASSES,
  HAIR_COLORS, HAIR_LENGTHS, HAIR_STYLES, HEIGHTS, LOOK_TABS, MARKS, OUTFIT_COLORS, OUTFITS, SKIN, VIBES,
} from "../options";
import s from "./steps.module.css";

type Attrs = Appearance["attributes"];
const withCurrent = (opts: { value: string; label: string }[], cur: string) =>
  cur && !opts.some((o) => o.value === cur) ? [...opts, { value: cur, label: cur }] : opts;

function Swatches({ label, options, value, onChange, allowNone }: { label: string; options: SwatchOpt[]; value: string | undefined; onChange: (v: string | undefined) => void; allowNone?: boolean }) {
  return (
    <fieldset className={s.swatchSet}>
      <legend className={s.fieldLabel}>{label}<span className={s.swatchName}>{value ?? "none"}</span></legend>
      <div className={s.swatches} role="radiogroup" aria-label={label}>
        {allowNone && (
          <button type="button" role="radio" aria-checked={!value} className={cx(s.swatch, s.swatchNone)} onClick={() => onChange(undefined)} aria-label="None" />
        )}
        {options.map((o) => (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={value === o.value || value === o.hex}
            aria-label={o.label}
            title={o.label}
            className={s.swatch}
            style={{ "--sw": o.hex } as CSSProperties}
            onClick={() => onChange(o.value)}
          />
        ))}
      </div>
    </fieldset>
  );
}

export function LookStep() {
  const { character: c, work, goStep, edit } = useWizard();
  const [tab, setTab] = useState<LookTab>("body");
  const a = work.w.attributes;
  const set = (path: [keyof Attrs, string?], v: unknown) => work.setAttr(path, v);
  const est = useEstimate(c ? { characterId: c.id, kind: "portrait_candidates" } : null);
  const hasBase = !!c?.appearance.basePortraitUrl;
  const changed = edit && work.w.dirty.look && hasBase;

  const generate = async () => {
    if (!c) return;
    const ok = await (work.dirty ? saveFirst() : Promise.resolve(true));
    if (!ok) return;
    const job = await startGeneration({ characterId: c.id, kind: "portrait_candidates" }, "Generate portrait");
    if (job) void goStep("portrait", { skipSave: true });
  };
  const { save } = useWizard();
  const saveFirst = () => save({ quiet: true, step: "portrait" });

  const panel = (() => {
    switch (tab) {
      case "body": return (
        <>
          <ChipGroup label="Age band" value={a.body.ageBand} options={AGE_BANDS} onChange={(v) => set(["body", "ageBand"], v)} />
          <p className={s.microNote}>No minor option: Horizon characters are adults.</p>
          <ChipGroup label="Build" value={a.body.build} options={withCurrent(BUILDS, a.body.build)} onChange={(v) => set(["body", "build"], v)} />
          <ChipGroup label="Height" value={a.body.height} options={withCurrent(HEIGHTS, a.body.height)} onChange={(v) => set(["body", "height"], v)} />
          <Swatches label="Skin tone" options={SKIN} value={a.body.skinTone} onChange={(v) => set(["body", "skinTone"], v ?? "beige")} />
        </>
      );
      case "face": return (
        <>
          <ChipGroup label="Face shape" value={a.face.shape} options={withCurrent(FACE_SHAPES, a.face.shape)} onChange={(v) => set(["face", "shape"], v)} />
          <ChipGroup label="Baseline expression" value={a.face.baseline} options={BASELINES} onChange={(v) => set(["face", "baseline"], v)} />
          <ChipGroup label="Marks" multiple max={3} value={a.face.marks} options={withCurrentMany(MARKS, a.face.marks)} onChange={(v) => set(["face", "marks"], v)} />
        </>
      );
      case "eyes": return (
        <>
          <ChipGroup label="Eye shape" value={a.eyes.shape} options={withCurrent(EYE_SHAPES, a.eyes.shape)} onChange={(v) => set(["eyes", "shape"], v)} />
          <Swatches label="Eye colour" options={EYE_COLORS} value={a.eyes.color} onChange={(v) => set(["eyes", "color"], v ?? "brown")} />
          <ChipGroup label="Glasses" value={a.eyes.glasses} options={GLASSES} onChange={(v) => set(["eyes", "glasses"], v)} />
        </>
      );
      case "hair": return (
        <>
          <ChipGroup label="Length" value={a.hair.length} options={withCurrent(HAIR_LENGTHS, a.hair.length)} onChange={(v) => set(["hair", "length"], v)} />
          <ChipGroup label="Style" value={a.hair.style} options={withCurrent(HAIR_STYLES, a.hair.style)} onChange={(v) => set(["hair", "style"], v)} />
          <Swatches label="Colour" options={HAIR_COLORS} value={a.hair.color} onChange={(v) => set(["hair", "color"], v ?? "black")} />
          <Swatches label="Streak" options={HAIR_COLORS} value={a.hair.streakColor} allowNone onChange={(v) => set(["hair", "streakColor"], v)} />
          <ChipGroup label="Fringe" value={a.hair.fringe} options={withCurrent(FRINGES, a.hair.fringe)} onChange={(v) => set(["hair", "fringe"], v)} />
        </>
      );
      case "outfit": return (
        <>
          <ChipGroup label="Archetype" value={a.outfit.archetype} options={withCurrent(OUTFITS, a.outfit.archetype)} onChange={(v) => set(["outfit", "archetype"], v)} />
          <Swatches label="Main colour · previews live" options={OUTFIT_COLORS} value={OUTFIT_COLORS.find((o) => o.hex === a.outfit.primaryColor)?.value ?? a.outfit.primaryColor} onChange={(v) => set(["outfit", "primaryColor"], OUTFIT_COLORS.find((o) => o.value === v)?.hex ?? a.outfit.primaryColor)} />
          <Swatches label="Second colour · previews live" options={OUTFIT_COLORS} value={OUTFIT_COLORS.find((o) => o.hex === a.outfit.secondaryColor)?.value ?? a.outfit.secondaryColor} onChange={(v) => set(["outfit", "secondaryColor"], OUTFIT_COLORS.find((o) => o.value === v)?.hex ?? a.outfit.secondaryColor)} />
        </>
      );
      case "accessories": return (
        <ChipGroup label="Accessories · up to 3" multiple max={3} value={a.accessories} options={withCurrentMany(ACCESSORIES, a.accessories)} onChange={(v) => set(["accessories"], v)} />
      );
      case "vibe": return (
        <ChipGroup label="Vibe · up to 2" multiple max={2} value={a.vibe} options={withCurrentMany(VIBES, a.vibe)} onChange={(v) => set(["vibe"], v)} />
      );
    }
  })();

  return (
    <>
      <section className={cx(s.work, s.lookWork)} aria-labelledby="look-h">
        <div className={s.stepHead}>
          <div>
            <Tape tone="ink" size="sm">Step 03 · Look</Tape>
            <h1 id="look-h" className={s.stepTitle}>Dress the part</h1>
          </div>
          <div className={s.stepHeadRight}>
            <span className={s.microNote}>AI pre-selected every chip from the seed. Nothing renders until you Generate.</span>
          </div>
        </div>
        {changed && (
          <div className={s.banner} role="status">
            <Tape tone="warn" size="sm">Appearance changed</Tape>
            <span>Regenerate portraits? The current base stays until you lock a new one.</span>
            <Button size="sm" variant="primary" cost={est ?? undefined} onClick={() => void generate()}>Regenerate</Button>
          </div>
        )}
        <Tabs label="Appearance category" tabs={LOOK_TABS.map((t) => ({ id: t, label: t }))} value={tab} onChange={setTab} idBase="look" />
        <div className={s.lookPanel} role="tabpanel" id={`look-panel-${tab}`} aria-labelledby={`look-tab-${tab}`} key={tab}>
          {panel}
        </div>
        <div className={s.lookFoot}>
          <TextArea
            label="Appearance summary"
            rows={2}
            value={work.w.summary}
            edited={work.w.summaryEdited}
            hint={work.w.summaryEdited ? "Edited by you: chips no longer rewrite it." : "Compiled from your picks. Edit freely."}
            onRegenerate={() => work.setSummary(compileSummary(a, work.w.profile.role), false)}
            regenerateLabel="Recompile from chips"
            onChange={(e) => work.setSummary(e.target.value)}
          />
          <TextArea label="Extra details" rows={2} maxLength={300} counter placeholder="e.g. a cherry-blossom hairpin, ink-stained fingers" value={a.extraDetails ?? ""} onChange={(e) => set(["extraDetails"], e.target.value)} />
        </div>
      </section>
      <ActionBar>
        <Button variant="secondary" onClick={() => void goStep("portrait")}>Next: Portrait ▸</Button>
        <Button variant="primary" size="lg" cost={est ?? undefined} onClick={() => void generate()}>
          {hasBase ? "Regenerate portrait ▸" : "Generate portrait ▸"}
        </Button>
      </ActionBar>
    </>
  );
}

function withCurrentMany(opts: { value: string; label: string }[], cur: string[]) {
  const extra = cur.filter((v) => !opts.some((o) => o.value === v)).map((v) => ({ value: v, label: v }));
  return [...opts, ...extra];
}
