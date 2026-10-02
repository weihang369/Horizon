// S05a SEED (CHR-02): one line, an optional intent, "Surprise me", Draft with AI or write it yourself. Owner: Builder B.
import { useEffect, useRef, useState } from "react";
import { openOverlay } from "@/app/layers";
import { reportError } from "@/app/errors";
import { client } from "@/client";
import { useSettings } from "@/client/hooks";
import type { Character } from "@/contract/types";
import { navigate } from "@/router";
import { Button, RansomText, Tape } from "@/ui";
import { ActionBar } from "../ActionBar";
import { seedDraft, useWizard } from "../context";
import { createdThisSession, rememberJob } from "../generate";
import { INTENTS, SEED_EXAMPLES, SURPRISE } from "../options";
import s from "./steps.module.css";

const MAX = 300;
/** Profile draft price (doc 06 §8 pricing table; no character exists yet to estimate against). */
const DRAFT_USD = 0.002;

export function SeedStep() {
  const { worldId, world } = useWizard();
  const settings = useSettings().data;
  const [seed, setSeed] = useState("");
  const [intent, setIntent] = useState<Character["intent"] | null>(null);
  const [busy, setBusy] = useState<"ai" | "self" | null>(null);
  const [ph, setPh] = useState(0);
  const surpriseAt = useRef(Math.floor(Math.random() * SURPRISE.length));
  const field = useRef<HTMLTextAreaElement>(null);
  seedDraft.text = busy ? "" : seed;
  seedDraft.intent = intent;
  useEffect(() => () => void Object.assign(seedDraft, { text: "", intent: null }), []);

  useEffect(() => {
    field.current?.focus({ preventScroll: true });
    const t = setInterval(() => setPh((x) => (x + 1) % SEED_EXAMPLES.length), 3200);
    return () => clearInterval(t);
  }, []);

  const start = async (mode: "ai" | "self") => {
    const text = seed.trim();
    if (!text && mode === "ai") return;
    if (settings && settings.openRouterKeyStatus !== "set") {
      openOverlay("O05", { reason: mode === "ai" ? "Drafting with AI needs your OpenRouter key." : "Creating a character needs your OpenRouter key." });
      return;
    }
    setBusy(mode);
    try {
      const { character, job } = await client.characters.createDraft(worldId, { seedPrompt: text, intent: intent ?? "other" });
      createdThisSession.add(character.id);
      if (mode === "self") await client.jobs.cancel(job.id);
      else rememberJob(job);
      navigate({ name: "wizard", worldId, characterId: character.id, step: "profile" }, { replace: true, transition: "none", force: true });
    } catch (err) {
      reportError(err, { context: "Drafting with AI needs your OpenRouter key." });
      setBusy(null);
    }
  };

  const surprise = () => {
    surpriseAt.current = (surpriseAt.current + 1) % SURPRISE.length;
    setSeed(SURPRISE[surpriseAt.current]);
    field.current?.focus();
  };

  return (
    <>
      <section className={s.work} aria-labelledby="seed-h">
        <div className={s.seed}>
          <Tape tone="ink" size="sm">Step 01 · Seed{world ? ` · ${world.name}` : ""}</Tape>
          <h1 id="seed-h" className={s.seedTitle}>
            <RansomText text="Who are we summoning?" size="clamp(40px, 4.6vw, 64px)" slam tone="mixed" />
          </h1>
          <p className={s.lede}>Type one line. The AI drafts a full profile, a look, a palette and a theme brief. You edit everything after.</p>
          <div className={s.seedBox}>
            <label htmlFor="seed-field" className="sr-only">Seed line</label>
            <textarea
              id="seed-field"
              ref={field}
              className={s.seedField}
              value={seed}
              maxLength={MAX}
              rows={2}
              placeholder={SEED_EXAMPLES[ph]}
              onChange={(e) => setSeed(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void start("ai");
                }
              }}
            />
            <span className={s.seedCount} aria-live="polite">{seed.length}/{MAX}</span>
            <button type="button" className={s.surprise} onClick={surprise}>
              <span aria-hidden="true">⚄</span> Surprise me
            </button>
          </div>
          <fieldset className={s.intents}>
            <legend className={s.kicker}>Intent <span className={s.optional}>optional</span></legend>
            <div className={s.intentRow} role="radiogroup" aria-label="Intent">
              {INTENTS.map((i) => (
                <button
                  key={i.value}
                  type="button"
                  role="radio"
                  aria-checked={intent === i.value}
                  className={s.intentCard}
                  onClick={() => setIntent(intent === i.value ? null : i.value)}
                >
                  <span className={s.intentLabel}>{i.label}</span>
                  <span className={s.intentHint}>{i.hint}</span>
                </button>
              ))}
            </div>
          </fieldset>
          <ul className={s.seedSteps} aria-label="What happens next">
            <li><b>01</b> AI draft</li>
            <li><b>02</b> You edit</li>
            <li><b>03</b> Portrait + faces</li>
            <li><b>04</b> Summon</li>
          </ul>
        </div>
      </section>
      <ActionBar backTo="exit">
        <Button variant="ghost" disabled={!!busy} onClick={() => void start("self")}>Write it myself</Button>
        <Button
          variant="primary"
          size="lg"
          disabled={!seed.trim() || !!busy}
          cost={DRAFT_USD}
          keyLocked={settings ? settings.openRouterKeyStatus !== "set" : false}
          onClick={() => void start("ai")}
        >
          {busy === "ai" ? "Drafting…" : "Draft with AI ▸"}
        </Button>
      </ActionBar>
    </>
  );
}
