// S05 Character Creation Wizard (doc 02 CHR epic: seed → AI draft → human edit → approve). Owner: Builder B.
// Layout (UXA §2.2): step rail 64 · spec card column 440/360 · work area · action bar 80. The wizard themes the
// whole app root with the provisional palette (R9, D-50). Leaving mid-wizard asks O13 via the router leave guard.
import { useCallback, useEffect, useMemo, useRef } from "react";
import type { ComponentType, CSSProperties } from "react";
import { openOverlay, toast } from "@/app/layers";
import { reportError } from "@/app/errors";
import { client } from "@/client";
import { useCharacter, useJob, useSettings, useWorld } from "@/client/hooks";
import type { CreationStep } from "@/contract/types";
import { navigate, setLeaveGuard } from "@/router";
import type { Route } from "@/router";
import { setAppPalette } from "@/theme";
import { EmptyState } from "@/ui";
import { WizardContext } from "./context";
import type { WizardCtx } from "./context";
import { createdThisSession, useCharacterJobs } from "./generate";
import { furthestReachable, gateFacts, laterStep, profileValid, reachable } from "./gates";
import { SpecCard } from "./SpecCard";
import { StepRail } from "./StepRail";
import { ApproveStep } from "./steps/ApproveStep";
import { EmotionsStep } from "./steps/EmotionsStep";
import { LookStep } from "./steps/LookStep";
import { PaletteStep } from "./steps/PaletteStep";
import { PortraitStep } from "./steps/PortraitStep";
import { ProfileStep } from "./steps/ProfileStep";
import { SeedStep } from "./steps/SeedStep";
import { ThemeStep } from "./steps/ThemeStep";
import { useWorking } from "./working";
import s from "./wizard.module.css";

type WizardRoute = Extract<Route, { name: "wizard" }>;


const STEPS: Record<CreationStep, ComponentType> = {
  seed: SeedStep, profile: ProfileStep, look: LookStep, portrait: PortraitStep,
  emotions: EmotionsStep, palette: PaletteStep, theme: ThemeStep, approve: ApproveStep,
};

export function WizardScreen({ route }: { route: WizardRoute }) {
  const cid = route.characterId ?? null;
  const q = useCharacter(cid);
  const c = cid ? q.data ?? null : null;
  const world = useWorld(route.worldId).data;
  const demo = useSettings().data?.demoMode ?? false;
  const work = useWorking(c);
  const jobs = useCharacterJobs(cid);
  const emotionJob = useJob(jobs.emotion_set).data ?? null;
  const edit = !!route.edit || c?.status === "approved";
  const step: CreationStep = route.step ?? (cid ? "profile" : "seed");

  const facts = useMemo(
    () => gateFacts(c, { profileOk: c ? profileValid(work.w.dirty.profile ? work.w.profile : c.profile) : false, emotionJob: emotionJob && emotionJob.status !== "cancelled" ? emotionJob : null }),
    [c, work.w.profile, emotionJob],
  );

  // ── Theme the app root with the provisional palette (R9, D-50) ───────────────
  const paletteId = c?.paletteId ?? null;
  useEffect(() => {
    setAppPalette(paletteId);
  }, [paletteId]);
  useEffect(() => () => setAppPalette(null), []);

  // ── Gate redirect: a URL past a gate lands on the furthest reachable step ────
  useEffect(() => {
    if (!c || edit) return;
    if (step === "seed") {
      navigate({ name: "wizard", worldId: route.worldId, characterId: c.id, step: "profile" }, { replace: true, transition: "none", force: true });
      return;
    }
    if (!reachable(step, facts)) {
      navigate({ name: "wizard", worldId: route.worldId, characterId: c.id, step: furthestReachable(facts) }, { replace: true, transition: "none", force: true });
    }
  }, [c?.id, step, edit]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Save / step navigation ───────────────────────────────────────────────────
  const latest = useRef({ c, work, step, edit });
  latest.current = { c, work, step, edit };

  const save = useCallback<WizardCtx["save"]>(async (opts = {}) => {
    const { c: cur, work: wk, edit: ed } = latest.current;
    if (!cur) return true;
    const patch = wk.patch() ?? {};
    if (!ed && cur.status !== "approved") {
      const nextStep = laterStep(cur.creationStep, opts.step ?? latest.current.step);
      if (nextStep !== cur.creationStep) patch.creationStep = nextStep;
    }
    if (!Object.keys(patch).length) return true;
    try {
      await client.characters.update(cur.id, patch);
      wk.markSaved("all");
      if (!opts.quiet) toast({ variant: "success", text: ed ? "Changes saved · they apply to new messages." : "Draft saved." });
      return true;
    } catch (err) {
      reportError(err, { retry: () => void save(opts) });
      return false;
    }
  }, []);

  const goStep = useCallback<WizardCtx["goStep"]>(async (to, opts = {}) => {
    const { c: cur, edit: ed } = latest.current;
    if (!cur) return;
    if (!opts.skipSave) {
      const ok = await save({ step: to, quiet: true });
      if (!ok) return;
    }
    navigate({ name: "wizard", worldId: route.worldId, characterId: cur.id, step: to, ...(ed ? { edit: true } : {}) }, { replace: true, transition: "none" });
  }, [route.worldId, save]);

  const exit = useCallback(() => {
    const cur = latest.current.c;
    if (cur && cur.status === "approved") navigate({ name: "profile", worldId: route.worldId, characterId: cur.id }, { transition: "slash-back" });
    else navigate({ name: "hub", worldId: route.worldId }, { transition: "slash-back" });
  }, [route.worldId]);

  // ── Leave guard (CHR-01 AC2 → O13) ───────────────────────────────────────────
  useEffect(() => setLeaveGuard((to) => {
    const { c: cur, work: wk } = latest.current;
    if (!cur) return true;
    if (to.name === "wizard" && to.worldId === route.worldId && to.characterId === cur.id) return true;
    const approved = cur.status === "approved";
    if (approved && !wk.dirty) return true;
    if (cur.deletedAt) return true;
    openOverlay("O13", {
      characterId: cur.id,
      onSave: async () => {
        if (await save({ quiet: true })) {
          toast({ variant: "success", text: approved ? "Changes saved · they apply to new messages." : `${cur.profile.name || "Draft"} saved as a draft.` });
          navigate(to, { force: true, transition: "slash-back" });
        }
      },
      onDiscard: async () => {
        if (!approved && createdThisSession.has(cur.id)) {
          try {
            const active = await client.jobs.listActive();
            await Promise.all(active.filter((j) => j.characterId === cur.id).map((j) => client.jobs.cancel(j.id)));
            await client.characters.delete(cur.id);
            createdThisSession.delete(cur.id);
            toast({ variant: "info", text: "Draft discarded." });
          } catch (err) {
            reportError(err);
          }
        } else {
          wk.reset(cur);
        }
        navigate(to, { force: true, transition: "slash-back" });
      },
    });
    return false;
  }), [route.worldId, save]);

  if (cid && q.status === "error" && !q.data) {
    return (
      <main className={s.missing} data-screen="S05">
        <EmptyState title="This draft is gone." body="It may have been discarded or deleted." action={{ label: "Back to the hub", run: () => navigate({ name: "hub", worldId: route.worldId }) }} />
      </main>
    );
  }

  const ctx: WizardCtx = { worldId: route.worldId, world, character: c, step, edit, work, jobs, facts, save, goStep, exit };
  const Step = STEPS[step];
  const wide = step === "approve";
  return (
    <WizardContext.Provider value={ctx}>
      <main
        className={s.root}
        data-screen="S05"
        data-step={step}
        style={{ "--top-inset": demo ? "28px" : "0px" } as CSSProperties}
        aria-label={edit ? `Edit ${c?.profile.name ?? "character"}` : "Character wizard"}
      >
        <div className={s.bg} aria-hidden="true">
          <span className={s.bgWord}>{edit ? "EDIT" : "SUMMON"}</span>
          <span className={s.bgStripe} />
          <span className={s.bgHalftone} />
        </div>
        <StepRail />
        {!wide && <SpecCard />}
        {cid && !c ? (
          <div className={s.loadingWork} aria-busy="true"><span className={s.scan} />LOADING DRAFT</div>
        ) : (
          <Step key={step} />
        )}
      </main>
    </WizardContext.Provider>
  );
}
