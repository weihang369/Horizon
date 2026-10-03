// S05b PROFILE (CHR-03 drafting state, CHR-04 edit profile = system prompt, CHR-05 prompt preview). Owner: Builder B.
import { useEffect, useMemo, useState } from "react";
import type { CSSProperties } from "react";
import { openOverlay } from "@/app/layers";
import { client } from "@/client";
import { useJob } from "@/client/hooks";
import type { CharacterProfile } from "@/contract/types";
import { Button, ErrorTape, Segmented, Skeleton, Tape, TextArea, TextField, Toggle } from "@/ui";
import { cx } from "@/ui/cx";
import { ActionBar } from "../ActionBar";
import { useWizard } from "../context";
import { Section, TagInput } from "../fields";
import { cancelJob, isRunning, rememberJob, startGeneration } from "../generate";
import { gateFrom, validateProfile } from "../gates";
import type { ProfileField } from "../options";
import s from "./steps.module.css";

/** A mock of the AI team's system prompt template (CHR-05: read-only, template is theirs). */
function composePrompt(p: CharacterProfile, advisory: boolean): string {
  const lines = [
    `You are ${p.title ? `${p.title} ` : ""}${p.name || "{name}"}, ${p.role || "{role}"}, age ${p.age}${p.pronouns ? ` (${p.pronouns})` : ""}.`,
    p.tagline && `Tagline: "${p.tagline}"`,
    p.personality.summary && `Personality: ${p.personality.summary}`,
    p.personality.traits.length ? `Traits: ${p.personality.traits.join(", ")}.` : "",
    p.backstory && `Backstory: ${p.backstory}`,
    `Speaking style: ${p.speakingStyle.summary || "natural"} Tone ${p.speakingStyle.tone || "neutral"}, ${p.speakingStyle.formality}.`,
    p.speakingStyle.quirks.length ? `Quirks: ${p.speakingStyle.quirks.join("; ")}.` : "",
    p.speakingStyle.catchphrases.length ? `Catchphrases: ${p.speakingStyle.catchphrases.map((c) => `"${c}"`).join(", ")}.` : "",
    p.expertise.length ? `Expertise: ${p.expertise.join(", ")}.` : "",
    p.goals && `Goals: ${p.goals}`,
    p.relationshipToUser && `Relationship to the user: ${p.relationshipToUser}.`,
    p.boundaries.length ? `Boundaries:\n${p.boundaries.map((b) => `- ${b}`).join("\n")}` : "",
    advisory ? "This is an AI simulation, not professional advice. Point the user to a qualified professional for real decisions." : "",
    "Stay in character. Keep replies conversational. All characters are adults.",
  ];
  return lines.filter(Boolean).join("\n");
}

export function ProfileStep() {
  const { character: c, jobs, work, goStep, facts, edit } = useWizard();
  const draftJob = useJob(jobs.profile_draft).data;
  const drafting = isRunning(draftJob);
  const failed = draftJob?.status === "failed";
  const p = work.w.profile;
  const errors = useMemo(() => validateProfile(p), [p]);
  const [touched, setTouched] = useState<Set<string>>(new Set());
  const [showPrompt, setShowPrompt] = useState(false);
  const [regen, setRegen] = useState<{ field: ProfileField; jobId: string } | null>(null);
  const regenJob = useJob(regen?.jobId).data;
  const edited = new Set(work.w.editedFields);

  // A regenerated field lands: copy just that field from the server copy (CHR-04 AC2).
  useEffect(() => {
    if (!regen || !regenJob || isRunning(regenJob) || !c) return;
    const field = regen.field;
    setRegen(null);
    if (regenJob.status !== "succeeded") return;
    void client.characters.get(c.id).then((fresh) => work.setField(field, fresh.profile[field], false));
  }, [regenJob?.status]); // eslint-disable-line react-hooks/exhaustive-deps

  const touch = (f: string) => setTouched((t) => (t.has(f) ? t : new Set(t).add(f)));
  const set = (f: keyof CharacterProfile, v: unknown) => {
    touch(f);
    work.setField(f, v);
  };
  const err = (f: keyof typeof errors) => (touched.has(f) ? errors[f] : undefined);

  const regenerate = (field: ProfileField) => {
    if (!c || regen) return;
    const go = async () => {
      const job = await startGeneration({ characterId: c.id, kind: "profile_regenerate", targetField: field }, `Regenerate ${field}`, { confirm: false });
      if (job) {
        rememberJob(job);
        setRegen({ field, jobId: job.id });
      }
    };
    if (edited.has(field)) {
      openOverlay("O03", { title: `Regenerate ${field}?`, body: "You edited this field. A fresh AI version will replace your text.", confirmLabel: "Regenerate", onConfirm: go });
    } else void go();
  };
  const regenProps = (field: ProfileField) => ({
    onRegenerate: () => regenerate(field),
    regenerateLabel: `Regenerate ${field}`,
    edited: edited.has(field),
    readOnly: regen?.field === field,
  });

  const gate = gateFrom("profile", facts);
  const revealing = work.w.revealKey > 0;
  const promptText = composePrompt(p, work.w.advisory);
  const tokens = Math.round(promptText.length / 4);

  return (
    <>
      <section className={cx(s.work, s.workScroll)} aria-labelledby="profile-h" aria-busy={drafting || undefined}>
        <div className={s.stepHead}>
          <div>
            <Tape tone="ink" size="sm">Step 02 · Profile = system prompt</Tape>
            <h1 id="profile-h" className={s.stepTitle}>{drafting ? "Drafting…" : edit ? "Edit the profile" : "Make them yours"}</h1>
          </div>
          <div className={s.stepHeadRight}>
            {edit && <Tape tone="warn" size="sm" rotate={-3}>Changes apply to new messages</Tape>}
            <Toggle checked={showPrompt} onChange={setShowPrompt} label="View as prompt" />
          </div>
        </div>

        {drafting && (
          <div className={s.drafting} role="status">
            <span className={s.scanStripe} aria-hidden="true" />
            <span className={s.draftingLabel}>DRAFTING<span className={s.dots}>…</span></span>
            <span className={s.draftingMeta}>{Math.round((draftJob?.progress ?? 0) * 100)} % · seed: “{c?.seedPrompt}”</span>
            <Button variant="ghost" size="sm" onClick={() => draftJob && void cancelJob(draftJob.id)}>Cancel draft</Button>
          </div>
        )}
        {failed && (
          <ErrorTape
            message="The draft didn't come back. Retry, or write it yourself (the form is yours either way)."
            code={draftJob?.error?.code}
            action={{ label: "Retry draft", run: () => c && void startGeneration({ characterId: c.id, kind: "profile_draft" }, "Draft with AI", { confirm: false }) }}
          />
        )}

        {showPrompt ? (
          <div className={s.prompt}>
            <div className={s.promptHead}>
              <span>systemPromptPreview</span>
              <span className={s.promptMeta}>≈ {tokens} tokens · read-only · mock template</span>
            </div>
            <pre className={s.promptBody}>{promptText}</pre>
          </div>
        ) : drafting ? (
          <div className={s.formGrid} aria-hidden="true">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className={s.section} style={{ "--i": i } as CSSProperties}>
                <Skeleton lines={i % 2 ? 4 : 3} height={i % 2 ? 40 : 18} />
              </div>
            ))}
          </div>
        ) : (
          <div key={work.w.revealKey} className={cx(s.formGrid, revealing && s.revealing)}>
            <Section title="Identity" kicker="* required" index={0}>
              <div className={s.row2}>
                <TextField label="Name *" value={p.name} maxLength={60} error={err("name")} edited={edited.has("name")} onChange={(e) => set("name", e.target.value)} onBlur={() => touch("name")} />
                <TextField label="Title" placeholder="Dr., Prof., Chef…" value={p.title ?? ""} maxLength={24} onChange={(e) => set("title", e.target.value)} />
              </div>
              <TextField label="Role *" value={p.role} maxLength={80} error={err("role")} edited={edited.has("role")} onChange={(e) => set("role", e.target.value)} onBlur={() => touch("role")} />
              <div className={s.row3}>
                <TextField
                  label="Age *"
                  type="number"
                  min={18}
                  max={120}
                  inputMode="numeric"
                  value={Number.isFinite(p.age) ? String(p.age) : ""}
                  error={errors.age && (touched.has("age") || p.age < 18) ? errors.age : undefined}
                  onChange={(e) => set("age", e.target.value === "" ? Number.NaN : Number(e.target.value))}
                />
                <TextField label="Pronouns" placeholder="she/her" value={p.pronouns ?? ""} maxLength={24} onChange={(e) => set("pronouns", e.target.value)} />
              </div>
              <TextField label="Tagline" counter maxLength={80} value={p.tagline} error={errors.tagline} {...regenProps("tagline")} onChange={(e) => set("tagline", e.target.value)} />
              <TextField label="Relationship to you" placeholder="your older sister, your rival…" value={p.relationshipToUser ?? ""} maxLength={80} hint="Free text. Not a link to another character." onChange={(e) => set("relationshipToUser", e.target.value)} />
              <div className={s.advisory}>
                <Toggle checked={work.w.advisory} onChange={work.setAdvisory} label="Advisory character" />
                <span className={s.fieldHint}>Auto-set for professional roles. Adds the "AI simulation · not professional advice" tape in chat.</span>
              </div>
            </Section>

            <Section title="Personality" index={1}>
              <TextArea label="Summary" rows={2} value={p.personality.summary} edited={edited.has("personality")} onChange={(e) => set("personality", { ...p.personality, summary: e.target.value })} />
              <TagInput
                label="Traits"
                value={p.personality.traits}
                min={3}
                max={8}
                error={errors.traits}
                edited={edited.has("personality")}
                placeholder="Add a trait, press Enter"
                onChange={(v) => set("personality", { ...p.personality, traits: v })}
              />
              <TextArea label="Backstory" rows={4} value={p.backstory} {...regenProps("backstory")} onChange={(e) => set("backstory", e.target.value)} />
            </Section>

            <Section title="Voice" kicker="Speaking style" index={2}>
              <TextArea label="How they talk" rows={2} value={p.speakingStyle.summary} onChange={(e) => set("speakingStyle", { ...p.speakingStyle, summary: e.target.value })} />
              <div className={s.row2}>
                <TextField label="Tone" placeholder="warm, dry, upbeat…" value={p.speakingStyle.tone} onChange={(e) => set("speakingStyle", { ...p.speakingStyle, tone: e.target.value })} />
                <div className={s.segField}>
                  <span className={s.fieldLabel}>Formality</span>
                  <Segmented
                    label="Formality"
                    value={p.speakingStyle.formality}
                    options={[{ value: "casual", label: "Casual" }, { value: "neutral", label: "Neutral" }, { value: "formal", label: "Formal" }]}
                    onChange={(v) => set("speakingStyle", { ...p.speakingStyle, formality: v })}
                  />
                </div>
              </div>
              <TagInput label="Quirks" value={p.speakingStyle.quirks} max={5} onChange={(v) => set("speakingStyle", { ...p.speakingStyle, quirks: v })} />
              <TagInput label="Catchphrases" value={p.speakingStyle.catchphrases} max={4} onChange={(v) => set("speakingStyle", { ...p.speakingStyle, catchphrases: v })} />
              <TextField label="Greeting" value={p.greeting} maxLength={200} {...regenProps("greeting")} onChange={(e) => set("greeting", e.target.value)} />
            </Section>

            <Section title="Mind" kicker="Expertise · goals · limits" index={3}>
              <TagInput label="Expertise" value={p.expertise} max={8} onChange={(v) => set("expertise", v)} />
              <TextArea label="Goals" rows={2} value={p.goals ?? ""} {...regenProps("goals")} onChange={(e) => set("goals", e.target.value)} />
              <TagInput label="Boundaries" rows value={p.boundaries} max={6} placeholder="Add a boundary, press Enter" onChange={(v) => set("boundaries", v)} />
              <TagInput label="Example lines" rows value={p.exampleLines ?? []} max={3} placeholder="Optional: a line they'd say" hint="0–3 lines. They steer the voice." onChange={(v) => set("exampleLines", v)} />
            </Section>
          </div>
        )}
      </section>
      <ActionBar note={!gate.ok && !drafting ? <span className={s.gateNote}>{gate.reason}</span> : undefined}>
        <Button variant="primary" size="lg" disabled={!gate.ok || drafting} title={gate.reason} onClick={() => void goStep("look")}>
          Next: Look ▸
        </Button>
      </ActionBar>
    </>
  );
}
