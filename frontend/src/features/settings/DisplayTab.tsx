// Settings → Display (SET-04, SET-12, APP-05): reduced motion, VFX intensity, flash intensity, parallax, text size and
// Presenter Mode. Every control writes the prefs store, which re-applies the root data attributes live; the preview
// card on the right reacts immediately. Owner: Builder A.
import { useEffect, useState } from "react";
import { PortraitCard } from "../../character/PortraitCard";
import { useCharacter } from "../../client/hooks";
import type { Emotion } from "../../contract/types";
import { useMotionPrefs } from "../../motion/prefs";
import { setPrefs, usePrefs } from "../../stores/prefs";
import { Segmented, Toggle } from "../../ui/Controls";
import { Tape } from "../../ui/Tape";
import { Row, Section } from "./parts";
import s from "./Settings.module.css";

const CYCLE: Emotion[] = ["happy", "surprised", "embarrassed", "neutral"];

export function DisplayTab() {
  const d = usePrefs((p) => p.display);
  const presenter = usePrefs((p) => p.presenterMode);
  const m = useMotionPrefs();
  return (
    <div className={s.split}>
      <div>
        <Section title="Motion">
          <Row label="Reduced motion" desc="System follows your OS. On: transitions become short fades; no shake, parallax, particles or flashes.">
            <Segmented label="Reduced motion" value={d.reducedMotion} onChange={(reducedMotion) => setPrefs({ display: { reducedMotion } })} options={[{ value: "system", label: "System" }, { value: "on", label: "On" }, { value: "off", label: "Off" }]} />
          </Row>
          <Row label="Emotion VFX" desc="Sparkles, rain, anger rings. Off keeps a static badge so tired and asleep still read.">
            <Segmented label="Emotion VFX" value={d.vfxIntensity} onChange={(vfxIntensity) => setPrefs({ display: { vfxIntensity } })} options={[{ value: "off", label: "Off" }, { value: "subtle", label: "Subtle" }, { value: "full", label: "Full" }]} />
          </Row>
          <Row label="Flash intensity" desc="Palette floods and stings. Low caps them at 35 %.">
            <Segmented label="Flash intensity" value={d.flashIntensity} onChange={(flashIntensity) => setPrefs({ display: { flashIntensity } })} options={[{ value: "off", label: "Off" }, { value: "low", label: "Low" }, { value: "full", label: "Full" }]} />
          </Row>
          <Row label="Parallax" desc="Portraits drift 6–10 px against the cursor.">
            <Toggle label="Parallax" hideLabel checked={d.parallax} onChange={(parallax) => setPrefs({ display: { parallax } })} />
          </Row>
        </Section>
        <Section title="Reading">
          <Row label="Text size" desc="Body text 14 / 16 / 18 px.">
            <Segmented label="Text size" value={d.textSize} onChange={(textSize) => setPrefs({ display: { textSize } })} options={[{ value: "s", label: "S" }, { value: "m", label: "M" }, { value: "l", label: "L" }]} />
          </Row>
          <Row label="Presenter Mode" desc="For demos and screen recordings: hides your key and the dev overlay, forces text size L, compact Insight drawer, shows ×N and REPLAY badges.">
            <Toggle label="Presenter Mode" hideLabel checked={presenter} onChange={(presenterMode) => setPrefs({ presenterMode })} />
          </Row>
        </Section>
      </div>
      <Preview reduced={m.reduced} vfx={m.vfx} textSize={presenter ? "l" : d.textSize} />
    </div>
  );
}

function Preview({ reduced, vfx, textSize }: { reduced: boolean; vfx: string; textSize: string }) {
  const hana = useCharacter("chr_seedHana").data;
  const [i, setI] = useState(0);
  useEffect(() => {
    const t = window.setInterval(() => setI((x) => (x + 1) % CYCLE.length), 2600);
    return () => window.clearInterval(t);
  }, []);
  return (
    <aside className={s.preview} aria-label="Live preview">
      <Tape tone="ink" size="sm">LIVE PREVIEW</Tape>
      {hana ? (
        <PortraitCard character={hana} emotion={CYCLE[i]} size="stage" width={220} showPlate showEnergy parallax />
      ) : (
        <div className={s.previewEmpty}>Preview needs the seed character Hana. Reset demo data to bring her back.</div>
      )}
      <p className={s.previewText}>“Welcome back!! I saved you the last peony.” <span>Text size {textSize.toUpperCase()}</span></p>
      <p className={s.previewMeta}>motion {reduced ? "reduced" : "full"} · vfx {vfx}</p>
    </aside>
  );
}
