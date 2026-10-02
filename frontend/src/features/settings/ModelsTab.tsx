// Settings → Models (SET-05, Advanced): editable model IDs for chat / decision / image / music, each with Test and an
// "Unverified model" warning when it differs from the default. Overrides are saved locally. Owner: Builder A.
import { useState } from "react";
import { openOverlay, toast } from "../../app/layers";
import { client } from "../../client";
import type { HorizonErrorShape } from "../../contract/errors";
import type { AppSettings, ModelSet } from "../../contract/types";
import { Button } from "../../ui/Button";
import { TextField } from "../../ui/Fields";
import { Tape } from "../../ui/Tape";
import { Section, useSettingsPatch } from "./parts";
import s from "./Settings.module.css";

const ROLES: { id: keyof ModelSet; label: string; desc: string }[] = [
  { id: "chat", label: "Main chat model", desc: "Every character line." },
  { id: "decision", label: "Decision model (System One)", desc: "Routing, emotions, who speaks next." },
  { id: "image", label: "Image model", desc: "Portraits and emotion edits." },
  { id: "music", label: "Music model", desc: "Theme songs." },
];

export function ModelsTab({ settings }: { settings: AppSettings }) {
  const defaults = settings.models;
  const effective = (r: keyof ModelSet) => settings.modelOverrides?.[r] ?? defaults[r];
  const [draft, setDraft] = useState<ModelSet>(() => ({ chat: effective("chat"), decision: effective("decision"), image: effective("image"), music: effective("music") }));
  const [results, setResults] = useState<Partial<Record<keyof ModelSet, string>>>({});
  const { save, saving } = useSettingsPatch();
  const dirty = ROLES.some((r) => draft[r.id].trim() !== effective(r.id));

  const test = async (role: keyof ModelSet) => {
    if (settings.demoMode) return openOverlay("O05", { reason: "Testing a model needs your OpenRouter key." });
    setResults((x) => ({ ...x, [role]: "Testing…" }));
    try {
      const r = await client.settings.testModel(role);
      setResults((x) => ({ ...x, [role]: `✓ ${r.model} · ${r.latencyMs} ms` }));
    } catch (e) {
      setResults((x) => ({ ...x, [role]: `✗ ${(e as HorizonErrorShape)?.message ?? "Failed"}` }));
    }
  };

  return (
    <Section
      title="Model IDs"
      desc="OpenRouter model slugs. Change these only if you know the replacement supports the same features. Overrides stay on this machine, never in committed config."
      aside={<Tape tone="warn" size="sm">ADVANCED</Tape>}
    >
      <div className={s.models}>
        {ROLES.map((r) => {
          const unverified = draft[r.id].trim() !== defaults[r.id];
          return (
            <div key={r.id} className={s.modelRow}>
              <TextField
                label={r.label}
                hint={results[r.id] ?? (unverified ? `Default: ${defaults[r.id]}` : r.desc)}
                value={draft[r.id]}
                spellCheck={false}
                onChange={(e) => setDraft((d) => ({ ...d, [r.id]: e.target.value }))}
                edited={unverified}
              />
              <div className={s.modelSide}>
                {unverified && <Tape tone="warn" size="sm">UNVERIFIED MODEL</Tape>}
                <Button size="sm" variant="secondary" keyLocked={settings.demoMode} onClick={() => void test(r.id)}>Test</Button>
              </div>
            </div>
          );
        })}
      </div>
      <div className={s.actionsRow}>
        <Button variant="ghost" onClick={() => { setDraft({ ...defaults }); void save({ modelOverrides: { ...defaults } }, "Models reset to defaults."); setResults({}); }}>Reset to defaults</Button>
        <Button disabled={!dirty || saving} onClick={() => {
          if (ROLES.some((r) => !draft[r.id].trim())) return toast({ variant: "warn", text: "Model IDs can't be empty." });
          void save({ modelOverrides: { chat: draft.chat.trim(), decision: draft.decision.trim(), image: draft.image.trim(), music: draft.music.trim() } }, "Model overrides saved.");
        }}>Save models</Button>
      </div>
    </Section>
  );
}
