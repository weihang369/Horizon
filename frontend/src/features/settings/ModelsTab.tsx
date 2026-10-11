// Settings → Models (SET-05, docs/ai/03 C9): a read-only "Models in use" panel. Horizon v1 is tuned for one model set
// (temperatures, length targets, Jev floors, cache layout), so model IDs aren't editable; each role shows its model,
// what it is for, its price from the bundled price table (the same source as seed/pricing.json) and Test, which
// probes the model the app actually uses. `modelOverrides` stays in the contract, unused, for v2.
import { useState } from "react";
import { openOverlay } from "../../app/layers";
import { client } from "../../client";
import type { HorizonErrorShape } from "../../contract/errors";
import type { AppSettings, ModelSet } from "../../contract/types";
import { PRICING } from "../../mock/pricing.config";
import { Button } from "../../ui/Button";
import { Tape } from "../../ui/Tape";
import { Section } from "./parts";
import s from "./Settings.module.css";

const perM = (usd: number) => `$${usd.toFixed(usd < 0.1 ? 3 : 2)} / M tokens`;
const each = (usd: number, what: string) => `$${usd.toFixed(3)} per ${what}`;

export const MODEL_ROLES: { id: keyof ModelSet; label: string; desc: string; price: string }[] = [
  { id: "chat", label: "Main chat model", desc: "Every character line, drafts and summaries.",
    price: `${perM(PRICING.chat.inputPerM)} in · ${perM(PRICING.chat.outputPerM)} out` },
  { id: "decision", label: "Decision model (System 1)", desc: "Who speaks, emotions, checks and scores.",
    price: `${perM(PRICING.decision.inputPerM)} in · output free` },
  { id: "image", label: "Image model", desc: "Portraits and emotion edits.", price: each(PRICING.generation.portrait, "image") },
  { id: "music", label: "Music model", desc: "Theme songs.", price: each(PRICING.generation.song, "30-second clip") },
  { id: "embedding", label: "Embedding model", desc: "Knowledge and memory search.", price: perM(PRICING.embedding.inputPerM) },
];

export function ModelsTab({ settings }: { settings: AppSettings }) {
  const [results, setResults] = useState<Partial<Record<keyof ModelSet, string>>>({});

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
      title="Models in use"
      desc="Tuned for these models. Custom models are planned for v2."
      aside={<Tape tone="paper" size="sm">READ-ONLY</Tape>}
    >
      <div className={s.models}>
        {MODEL_ROLES.map((r) => (
          <div key={r.id} className={s.modelRow} data-role={r.id}>
            <div>
              <div className={s.modelLabel}>{r.label}</div>
              <code className={s.modelSlug}>{settings.models[r.id]}</code>
              <div className={s.modelHint}>{results[r.id] ?? r.desc}</div>
              <div className={s.modelHint} data-price>{r.price}</div>
            </div>
            <div className={s.modelSide}>
              <Button size="sm" variant="secondary" keyLocked={settings.demoMode} onClick={() => void test(r.id)}>Test</Button>
            </div>
          </div>
        ))}
      </div>
    </Section>
  );
}
