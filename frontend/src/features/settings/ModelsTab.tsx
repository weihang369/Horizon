// Settings → Models (SET-05, docs/ai/03 C9): a read-only "Models in use" panel. Horizon v1 is tuned for one model set
// (temperatures, length targets, Jev floors, cache layout), so model IDs aren't editable; each role is a card with its
// model, what it is for and its price from the bundled price table (the same source as seed/pricing.json). No Test
// button: a probe is a paid call that tells the user nothing Connection's Test doesn't (D-107; testModel stays in the
// contract). `modelOverrides` stays in the contract, unused, for v2.
import type { AppSettings, ModelSet } from "../../contract/types";
import { PRICING } from "../../mock/pricing.config";
import { Tape } from "../../ui/Tape";
import { Section } from "./parts";
import s from "./Settings.module.css";

const perM = (usd: number) => `$${usd.toFixed(usd < 0.1 ? 3 : 2)} / M tokens`;
const each = (usd: number, what: string) => `$${usd.toFixed(3)} per ${what}`;

export const MODEL_ROLES: { id: keyof ModelSet; label: string; desc: string; price: string }[] = [
  { id: "chat", label: "Main chat", desc: "Every character line, drafts and summaries.",
    price: `${perM(PRICING.chat.inputPerM)} in · ${perM(PRICING.chat.outputPerM)} out` },
  { id: "decision", label: "Decision · System 1", desc: "Who speaks, emotions, checks and scores.",
    price: `${perM(PRICING.decision.inputPerM)} in · output free` },
  { id: "image", label: "Image", desc: "Portraits and emotion edits.", price: each(PRICING.generation.portrait, "image") },
  { id: "music", label: "Music", desc: "Theme songs.", price: each(PRICING.generation.song, "30-second clip") },
  { id: "embedding", label: "Embedding", desc: "Knowledge and memory search.", price: perM(PRICING.embedding.inputPerM) },
];

export function ModelsTab({ settings }: { settings: AppSettings }) {
  return (
    <Section
      title="Models in use"
      className={s.modelsSection}
      desc="Tuned for these models. Custom models are planned for v2."
      aside={<Tape tone="paper" size="sm">READ-ONLY</Tape>}
    >
      <ul className={s.models}>
        {MODEL_ROLES.map((r) => {
          const slug = settings.models[r.id];
          const cut = slug.indexOf("/") + 1;
          return (
            <li key={r.id} className={s.modelCard} data-role={r.id}>
              <span className={s.modelLabel}>{r.label}</span>
              <span className={s.modelSlug} title={slug}>
                <span className={s.modelProvider}>{slug.slice(0, cut)}</span>
                <span className={s.modelName}>{slug.slice(cut)}</span>
              </span>
              <span className={s.modelDesc}>{r.desc}</span>
              <span className={s.modelPrice} data-price>{r.price}</span>
            </li>
          );
        })}
      </ul>
    </Section>
  );
}
