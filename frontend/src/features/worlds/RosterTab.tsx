// S04 Roster tab (WLD-05 AC3/AC4, ENG-01, PRF-06): portrait cards with plate, energy, tagline, quick Chat and the
// background-job pill slot; drafts resume the wizard; "Archived" filter with Restore / Delete permanently. Owner: Builder A.
import type { ComponentType } from "react";
import { openOverlay, toast } from "../../app/layers";
import { PortraitCard } from "../../character/PortraitCard";
import { client } from "../../client";
import type { HorizonErrorShape } from "../../contract/errors";
import type { Character, Session } from "../../contract/types";
import type { Route } from "../../router";
import { navigate } from "../../router";
import { getPalette } from "../../theme/palettes";
import { Button } from "../../ui/Button";
import { Chip } from "../../ui/Controls";
import { EmptyState } from "../../ui/Panels";
import { Tape } from "../../ui/Tape";
import { JobPill as JobPillImpl } from "../profile/JobPill";
import s from "./Hub.module.css";

/** Builder B owns the pill; the roster passes the card's job so the pill can render compactly in its slot. */
const JobPill = JobPillImpl as unknown as ComponentType<{ jobId?: string; characterId?: string; variant?: "card" }>;

interface Props {
  worldId: string;
  route: Extract<Route, { name: "hub" }>;
  chars: Character[];
  loading: boolean;
  sessions: Session[];
  demo: boolean;
}

const STEP_LABEL: Record<string, string> = {
  seed: "Seed", profile: "Profile", look: "Look", portrait: "Portrait", emotions: "Emotions", palette: "Palette", theme: "Theme", approve: "Approve",
};

export function RosterTab({ worldId, route, chars, loading, sessions, demo }: Props) {
  const archivedView = route.filter === "archived";
  const approved = chars.filter((c) => c.status === "approved");
  const drafts = chars.filter((c) => c.status === "draft" || c.status === "review");
  const archived = chars.filter((c) => c.status === "archived");
  const setFilter = (archivedOn: boolean) =>
    navigate({ name: "hub", worldId, ...(archivedOn ? { filter: "archived" } : {}) }, { transition: "none", replace: true });

  const chat = async (c: Character) => {
    if (demo) {
      openOverlay("O05", { reason: `Chatting with ${c.profile.name.split(" ")[0]} needs your OpenRouter key. Their recorded sessions still play.` });
      return;
    }
    const existing = sessions
      .filter((x) => x.mode === "one_on_one" && x.status !== "ended" && !x.isSeed && x.participants.some((p) => p.characterId === c.id))
      .sort((a, b) => Date.parse(b.updatedAt) - Date.parse(a.updatedAt))[0];
    if (existing) return navigate({ name: "session", worldId, sessionId: existing.id });
    try {
      const snap = await client.sessions.create({ worldId, mode: "one_on_one", characterIds: [c.id] });
      navigate({ name: "session", worldId, sessionId: snap.session.id });
    } catch (e) {
      const err = e as HorizonErrorShape;
      if (err?.code === "missing_key" || err?.code === "invalid_key") openOverlay("O05", {});
      else toast({ variant: "error", text: err?.message ?? "Couldn't start the chat." });
    }
  };

  const restore = async (c: Character) => {
    try {
      await client.characters.restore(c.id);
      toast({ variant: "success", text: `${c.profile.name} is back on the roster.` });
    } catch (e) {
      toast({ variant: "error", text: (e as HorizonErrorShape)?.message ?? "Couldn't restore." });
    }
  };
  const deleteForever = (c: Character) =>
    openOverlay("O03", {
      title: `Delete ${c.profile.name} permanently?`,
      body: "Their portraits, theme song, memories and knowledge go too. Sessions they joined keep their lines.",
      typed: c.profile.name,
      confirmLabel: "Delete permanently",
      onConfirm: async () => {
        await client.characters.delete(c.id);
        toast({ variant: "info", text: `${c.profile.name} was deleted.` });
      },
    });

  return (
    <div className={s.roster}>
      <div className={s.toolbar}>
        <p className={s.toolbarTitle}>
          {archivedView ? "Archived characters" : `${approved.length} character${approved.length === 1 ? "" : "s"}`}
          {!archivedView && drafts.length > 0 && <span className={s.toolbarDim}> · {drafts.length} in the wizard</span>}
        </p>
        <div className={s.toolbarChips} role="group" aria-label="Roster filter">
          <Chip size="sm" selected={!archivedView} onClick={() => setFilter(false)}>Roster</Chip>
          <Chip size="sm" selected={archivedView} onClick={() => setFilter(true)}>Archived · {archived.length}</Chip>
        </div>
      </div>

      {loading ? (
        <ul className={s.grid} aria-busy="true" aria-label="Loading characters">
          {[0, 1, 2, 3].map((i) => <li key={i} className={s.cardSkeleton} />)}
        </ul>
      ) : archivedView ? (
        archived.length === 0 ? (
          <EmptyState title="No archived characters" className={s.empty} />
        ) : (
          <ul className={s.grid}>
            {archived.map((c, i) => (
              <li key={c.id} className={`${s.rc} ${s.rcArchived}`} style={{ ["--i" as string]: i }}>
                <PortraitCard character={c} emotion="neutral" size="card" width={236} showPlate dimmed />
                <Tape tone="ink" size="sm" className={s.rcTape}>ARCHIVED</Tape>
                <div className={s.rcBody}>
                  <p className={s.tagline}>{c.profile.tagline}</p>
                  <div className={s.rcActions}>
                    <Button size="sm" variant="secondary" onClick={() => void restore(c)}>Restore</Button>
                    <Button size="sm" variant="ghost" onClick={() => deleteForever(c)}>Delete permanently</Button>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )
      ) : approved.length === 0 && drafts.length === 0 ? (
        <EmptyState
          title="This world is quiet"
          body="Summon someone."
          className={s.empty}
          action={{ label: "+ New Character", run: () => navigate({ name: "wizard", worldId }) }}
        />
      ) : (
        <ul className={s.grid}>
          {approved.map((c, i) => (
            <li key={c.id} className={s.rc} style={{ ["--i" as string]: i }}>
              <span className={s.stripeBar} style={{ background: getPalette(c.paletteId).primary }} aria-hidden="true" />
              <PortraitCard
                character={c}
                emotion="neutral"
                size="card"
                width={236}
                showPlate
                showEnergy
                parallax
                aria-label={`${c.profile.name}, ${c.profile.role}. Open profile`}
                onClick={() => navigate({ name: "profile", worldId, characterId: c.id })}
              />
              {c.activeJobId && (
                <div className={s.jobSlot}>
                  <JobPill jobId={c.activeJobId} characterId={c.id} variant="card" />
                </div>
              )}
              <div className={s.rcBody}>
                <p className={s.tagline} title={c.profile.tagline}>{c.profile.tagline}</p>
                <div className={s.rcActions}>
                  <Button size="sm" keyLocked={demo} onClick={() => void chat(c)}>Chat</Button>
                  <Button size="sm" variant="ghost" onClick={() => navigate({ name: "profile", worldId, characterId: c.id })}>Profile</Button>
                </div>
              </div>
            </li>
          ))}
          {drafts.map((c, i) => (
            <li key={c.id} className={`${s.rc} ${s.rcDraft}`} style={{ ["--i" as string]: approved.length + i }}>
              <PortraitCard
                character={c}
                emotion="neutral"
                size="card"
                width={236}
                showPlate
                aria-label={`${c.profile.name || "Untitled"}: draft. Resume in the wizard`}
                onClick={() => navigate({ name: "wizard", worldId, characterId: c.id, step: c.creationStep })}
              />
              <Tape tone="paper" size="sm" className={s.rcTape}>
                {c.status === "review" ? "IN REVIEW" : `DRAFT · ${STEP_LABEL[c.creationStep ?? "seed"].toUpperCase()}`}
              </Tape>
              {c.activeJobId && (
                <div className={s.jobSlot}>
                  <JobPill jobId={c.activeJobId} characterId={c.id} variant="card" />
                </div>
              )}
              <div className={s.rcBody}>
                <p className={s.tagline}>{c.profile.tagline || c.seedPrompt}</p>
                <div className={s.rcActions}>
                  <Button size="sm" variant="secondary" onClick={() => navigate({ name: "wizard", worldId, characterId: c.id, step: c.creationStep })}>Resume ▸</Button>
                </div>
              </div>
            </li>
          ))}
          <li className={s.rcNew} style={{ ["--i" as string]: approved.length + drafts.length }}>
            <button type="button" className={s.newChar} onClick={() => navigate({ name: "wizard", worldId })}>
              <span className={s.newCharPlus} aria-hidden="true">+</span>
              <span className={s.newCharLabel}>New Character</span>
              <span className={s.newCharHint}>Describe someone in one line.</span>
            </button>
          </li>
        </ul>
      )}
    </div>
  );
}
