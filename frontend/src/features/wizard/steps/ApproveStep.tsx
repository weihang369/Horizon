// S05h APPROVE (CHR-11): summary card (portrait, plate, role, tagline, palette, emotion thumbs, song, warnings) and
// "Approve & Summon" → O15. Editing an approved character ends with "Save changes" instead (PRF-03 AC4). Owner: Builder B.
import { useState } from "react";
import type { CSSProperties } from "react";
import { openOverlay, toast } from "@/app/layers";
import { reportError } from "@/app/errors";
import { client } from "@/client";
import { useJob, useSong } from "@/client/hooks";
import { EMOTIONS } from "@/contract/types";
import { emotionMeta, PortraitCard } from "@/character";
import { navigate } from "@/router";
import { getPalette } from "@/theme";
import { Button, RansomText, Tape } from "@/ui";
import { cx } from "@/ui/cx";
import { Composing, ThemePlayer } from "@/features/profile/ThemePlayer";
import { ActionBar } from "../ActionBar";
import { useWizard } from "../context";
import { createdThisSession, isRunning } from "../generate";
import { canApprove, missingEmotions, validateProfile } from "../gates";
import s from "./steps.module.css";

export function ApproveStep() {
  const { character: c, work, facts, edit, save, worldId, jobs, goStep } = useWizard();
  const song = useSong(c?.id).data;
  const songJob = useJob(jobs.song).data;
  const emoJob = useJob(jobs.emotion_set).data;
  const [busy, setBusy] = useState(false);
  if (!c) return null;

  const p = work.w.profile;
  const pal = getPalette(c.paletteId);
  const missing = missingEmotions(c);
  const composing = isRunning(songJob);
  const errs = validateProfile(p);
  const ok = canApprove(facts);
  const pc = { ...c, profile: { ...c.profile, name: p.name, role: p.role } };

  const approve = async () => {
    setBusy(true);
    try {
      if (!(await save({ quiet: true }))) return;
      await client.characters.approve(c.id);
      createdThisSession.delete(c.id);
      openOverlay("O15", { characterId: c.id });
      navigate({ name: "profile", worldId, characterId: c.id }, { force: true, transition: "none" });
    } catch (err) {
      reportError(err);
    } finally {
      setBusy(false);
    }
  };
  const saveChanges = async () => {
    setBusy(true);
    if (await save({ quiet: true })) {
      toast({ variant: "success", text: "Changes saved · they apply to new messages." });
      navigate({ name: "profile", worldId, characterId: c.id }, { force: true, transition: "slash-back" });
    }
    setBusy(false);
  };

  const warnings: { tone: "warn" | "error"; text: string; fix?: () => void; fixLabel?: string }[] = [];
  if (errs.name || errs.role || errs.age) warnings.push({ tone: "error", text: Object.values(errs)[0]!, fix: () => void goStep("profile"), fixLabel: "Fix profile" });
  if (!c.appearance.basePortraitUrl) warnings.push({ tone: "error", text: "No locked base portrait yet.", fix: () => void goStep("portrait"), fixLabel: "Go to Portrait" });
  if (missing.length) warnings.push({ tone: "warn", text: `${missing.length} emotion${missing.length > 1 ? "s" : ""} missing${isRunning(emoJob) ? " (still painting)" : ""}: they fall back to neutral + VFX.` });
  if (!song || (song.status !== "ready" && !composing)) warnings.push({ tone: "warn", text: "No theme song: the ambient bed plays instead." });
  if (composing) warnings.push({ tone: "warn", text: "Theme still composing: the reveal uses the ambient bed; we'll ping you when it's ready." });

  return (
    <>
      <section className={cx(s.work, s.approveWork)} aria-labelledby="approve-h">
        <div className={s.approveCard}>
          <div className={s.approvePortrait}>
            <PortraitCard character={pc} emotion="neutral" size="hero" width="var(--ap-w)" showPlate />
          </div>
          <div className={s.approveInfo}>
            <Tape tone="ink" size="sm">Step 08 · {edit ? "Review changes" : "Ready to summon"}</Tape>
            <h1 id="approve-h" className={s.approveName}>
              <RansomText text={p.name || "Unnamed"} size="clamp(44px, 4.4vw, 68px)" tone="mixed" />
            </h1>
            <p className={s.approveRole}>{p.title ? `${p.title} · ` : ""}{p.role || "No role yet"} · {Number.isFinite(p.age) ? p.age : "?"}{p.pronouns ? ` · ${p.pronouns}` : ""}</p>
            {p.tagline && <p className={s.approveTagline}>“{p.tagline}”</p>}
            <div className={s.approveRow}>
              <span className={s.kicker}>Palette</span>
              <span className={s.palChip} style={{ "--a": pal.primary, "--b": pal.secondary, "--c": pal.accent } as CSSProperties}><i /><i /><i />{pal.name}</span>
            </div>
            <div className={s.approveRow}>
              <span className={s.kicker}>Faces</span>
              <div className={s.thumbs}>
                {EMOTIONS.map((e) => (
                  <span key={e} className={cx(s.thumb, !c.emotions[e] && s.thumbMissing)} title={`${emotionMeta[e].label}${c.emotions[e] ? "" : " (missing)"}`}>
                    {c.emotions[e] ? <img src={c.emotions[e]!.url} alt={emotionMeta[e].label} draggable={false} /> : <span aria-label={`${emotionMeta[e].label} missing`}>{emotionMeta[e].icon}</span>}
                  </span>
                ))}
              </div>
            </div>
            <div className={s.approveSong}>
              {composing && songJob ? <Composing progress={songJob.progress} /> : song?.status === "ready" ? <ThemePlayer song={song} characterName={p.name || "Their"} compact /> : null}
            </div>
            {warnings.length > 0 && (
              <ul className={s.warnings}>
                {warnings.map((w, i) => (
                  <li key={i} className={cx(s.warning, w.tone === "error" && s.warningErr)}>
                    <span className={s.warnMark} aria-hidden="true">{w.tone === "error" ? "✕" : "!"}</span>
                    <span>{w.text}</span>
                    {w.fix && <Button size="sm" variant="ghost" onClick={w.fix}>{w.fixLabel}</Button>}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </section>
      <ActionBar note={!ok ? <span className={s.gateNote}>Approve needs a valid profile and a locked base portrait.</span> : undefined}>
        {edit ? (
          <Button variant="primary" size="lg" disabled={busy || !ok} onClick={() => void saveChanges()}>Save changes</Button>
        ) : (
          <Button variant="primary" size="lg" className={s.summonBtn} disabled={busy || !ok} onClick={() => void approve()}>
            {busy ? "Summoning…" : "Approve & Summon ▸"}
          </Button>
        )}
      </ActionBar>
    </>
  );
}
