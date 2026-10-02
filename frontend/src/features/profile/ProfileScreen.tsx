// S06 Character Profile (PRF-01..09, ENG-01/03/05/06). Owner: Builder B.
// Left: the large animated portrait card with the energy panel under it. Right: name, CTAs and six tabs
// (Profile · Gallery · Theme · Sessions · Memory · Knowledge). Single-character screen → the whole app root wears
// the character's palette (R9) with a flood on entry (R10); the theme song starts (PRF-01 AC2, MUS-02).
import { useEffect, useMemo, useState } from "react";
import type { CSSProperties } from "react";
import { audio } from "@/audio/engine";
import { reportError } from "@/app/errors";
import { isOverlayOpen, openOverlay, toast } from "@/app/layers";
import { useShortcut } from "@/app/shortcuts";
import { client } from "@/client";
import { useCharacter, useEnergy, useNow, useRushHour, useSettings, useSong, useWorld } from "@/client/hooks";
import type { Emotion } from "@/contract/types";
import { EnergyBar, NamePlate, PortraitCard } from "@/character";
import { formatUntil, formatUsd } from "@/domain/format";
import { navigate, PROFILE_TABS } from "@/router";
import type { ProfileTab, Route } from "@/router";
import { setAppPalette } from "@/theme";
import { Button, EmptyState, RansomText, Segmented, Skeleton, Tabs, Tape } from "@/ui";
import { cx } from "@/ui/cx";
import { JobPill } from "./JobPill";
import { GalleryTab, KnowledgeTab, MemoryTab, ProfileTabView, SessionsTab, ThemeTab } from "./tabs";
import { themeLabel } from "./ThemePlayer";
import s from "./profile.module.css";

type ProfileRoute = Extract<Route, { name: "profile" }>;
const AMBIENT = "placeholder:system/ambient_bed";
const TAB_LABEL: Record<ProfileTab, string> = { profile: "Profile", gallery: "Gallery", theme: "Theme", sessions: "Sessions", memory: "Memory", knowledge: "Knowledge" };

export function ProfileScreen({ route }: { route: ProfileRoute }) {
  const q = useCharacter(route.characterId);
  const c = q.data;
  const world = useWorld(route.worldId).data;
  const song = useSong(route.characterId).data;
  const demo = useSettings().data?.demoMode ?? false;
  const energy = useEnergy(route.characterId);
  const rush = useRushHour();
  const now = useNow(30_000);
  const tab: ProfileTab = route.tab ?? "profile";
  const [preview, setPreview] = useState<Emotion | null>(null);

  // ── Palette: flood the app root on entry (R9/R10); the Summon ceremony does its own ──
  const paletteId = c?.paletteId;
  useEffect(() => {
    if (!paletteId) return;
    if (isOverlayOpen("O15")) setAppPalette(paletteId);
    else setAppPalette(paletteId, { flood: { x: Math.round(window.innerWidth * 0.22), y: Math.round(window.innerHeight * 0.55) } });
  }, [paletteId]);
  useEffect(() => () => setAppPalette(null), []);

  // ── Music: the character's theme (ambient bed until one exists, MUS-07) ──
  const songUrl = song?.status === "ready" ? song.url : undefined;
  const name = c?.profile.name;
  useEffect(() => {
    if (!name || isOverlayOpen("O15")) return;
    if (songUrl) audio.setMusic(songUrl, { label: themeLabel(name), gainDb: song?.gainDb });
    else if (song !== undefined) audio.setMusic(AMBIENT, { label: "Ambient bed" });
  }, [songUrl, name, song === undefined]); // eslint-disable-line react-hooks/exhaustive-deps

  const setTab = (t: ProfileTab) => navigate({ ...route, tab: t === "profile" ? undefined : t }, { replace: true, transition: "none" });
  useShortcut("[", () => setTab(PROFILE_TABS[(PROFILE_TABS.indexOf(tab) + PROFILE_TABS.length - 1) % PROFILE_TABS.length]));
  useShortcut("]", () => setTab(PROFILE_TABS[(PROFILE_TABS.indexOf(tab) + 1) % PROFILE_TABS.length]));

  const topUp = () => openOverlay("O27", { characterId: route.characterId });
  const chat = async () => {
    if (!c) return;
    try {
      const list = await client.sessions.list(route.worldId);
      const existing = list
        .filter((x) => x.mode === "one_on_one" && !x.isSeed && x.status !== "ended" && x.participants.some((p) => p.characterId === c.id))
        .sort((a, b) => (b.lastMessageAt ?? b.updatedAt).localeCompare(a.lastMessageAt ?? a.updatedAt))[0];
      if (existing) return navigate({ name: "session", worldId: route.worldId, sessionId: existing.id });
      const snap = await client.sessions.create({ worldId: route.worldId, mode: "one_on_one", characterIds: [c.id] });
      navigate({ name: "session", worldId: route.worldId, sessionId: snap.session.id });
    } catch (err) {
      reportError(err, { context: `Chatting with ${c.profile.name} needs your OpenRouter key.` });
    }
  };
  const archive = async () => {
    if (!c) return;
    try {
      await client.characters.archive(c.id);
      toast({ variant: "info", text: `${c.profile.name} archived. History stays intact.`, action: { label: "Undo", run: () => void client.characters.restore(c.id).catch(reportError) } });
      navigate({ name: "hub", worldId: route.worldId }, { transition: "slash-back" });
    } catch (err) {
      reportError(err);
    }
  };
  const restore = async () => {
    if (!c) return;
    try {
      await client.characters.restore(c.id);
      toast({ variant: "success", text: `${c.profile.name} is back on the roster.` });
    } catch (err) {
      reportError(err);
    }
  };

  const tabs = useMemo(() => PROFILE_TABS.map((t) => ({ id: t, label: TAB_LABEL[t] })), []);

  if (q.status === "error" && !c) {
    return (
      <main className={s.missing} data-screen="S06">
        <EmptyState title="Character not found." body="They may have been deleted." action={{ label: "Back to the hub", run: () => navigate({ name: "hub", worldId: route.worldId }) }} />
      </main>
    );
  }

  const draft = c?.status === "draft" || c?.status === "review";
  const archived = c?.status === "archived";
  const state = energy?.state ?? c?.energy.state ?? "active";
  const first = c?.profile.name.split(" ")[0] ?? "";

  return (
    <main className={s.root} data-screen="S06" style={{ "--top-inset": demo ? "28px" : "0px" } as CSSProperties} aria-label={c ? `${c.profile.name}, profile` : "Character profile"}>
      <div className={s.bg} aria-hidden="true">
        <span className={s.bgBand} />
        <span className={s.bgHalftone} />
        <span className={s.bgName}>{first.toUpperCase()}</span>
      </div>

      <header className={s.top}>
        <button type="button" className={s.back} onClick={() => navigate({ name: "hub", worldId: route.worldId }, { transition: "slash-back" })} aria-label="Back to the hub">◂</button>
        <div className={s.crumb}>
          <span className={s.crumbWorld}>{world?.name ?? "…"}</span>
          <span className={s.crumbSep}>/</span>
          <span>Roster</span>
          <span className={s.crumbSep}>/</span>
          <span className={s.crumbHere}>{c?.profile.name ?? "…"}</span>
        </div>
        {c && <JobPill characterId={c.id} size="md" />}
      </header>

      <section className={s.left} aria-label="Portrait and energy">
        <div className={s.portrait}>
          {c ? (
            <PortraitCard
              character={c}
              emotion={preview ?? "neutral"}
              size="hero"
              width="var(--pf-w)"
              energyState={state}
              parallax
            />
          ) : (
            <div className={s.portraitSkel}><Skeleton lines={1} height={40} /></div>
          )}
          {c && <NamePlate className={s.plate} character={c} size="lg" subtitle={state === "exhausted" ? `Exhausted · back in ${formatUntil(energy?.fullAt, now) || "a while"}` : c.profile.title ? `${c.profile.title} · ${c.profile.role}` : c.profile.role} />}
          {draft && <span className={s.draftTape}><Tape tone="warn" rotate={-6}>Draft · {c?.creationStep ?? "profile"}</Tape></span>}
          {archived && <span className={s.draftTape}><Tape tone="ink" rotate={-6}>Archived</Tape></span>}
        </div>

        {c && (
          <div className={s.energy} aria-label="Energy">
            <div className={s.energyHead}>
              <span className={s.energyTitle}>⚡ Energy</span>
              <span className={cx(s.energyState, s[`st_${state}`])}>{state === "exhausted" ? "Asleep" : state === "tired" ? "Tired" : "Active"}</span>
              {rush.peak && <span className={s.rush} title="DeepSeek peak pricing">RUSH HOUR · replies cost 2× ⚡</span>}
            </div>
            <EnergyBar characterId={c.id} size="chat" showLabel onTopUp={topUp} label={c.profile.name} />
            <dl className={s.energyStats}>
              <div><dt>Spent today</dt><dd>⚡ {c.energy.spentToday} <span>≈ {formatUsd(c.energy.spentToday * 0.0001)}</span></dd></div>
              <div><dt>{energy && energy.current >= energy.max ? "Status" : "Full in"}</dt><dd>{energy && energy.current >= energy.max ? "Full" : demo ? "Frozen in demo" : formatUntil(energy?.fullAt, now) || "—"}</dd></div>
              <div><dt>Regen</dt><dd>+{Math.round((energy?.max ?? c.energy.max) / 24)} ⚡/h</dd></div>
            </dl>
            <div className={s.energyRow}>
              <Segmented
                label="Daily max"
                value={String(c.energy.max) as "500" | "1000" | "2000"}
                options={[{ value: "500", label: "500" }, { value: "1000", label: "1000" }, { value: "2000", label: "2000" }]}
                onChange={(v) => void client.characters.setEnergyMax(c.id, Number(v)).catch(reportError)}
              />
              <Button size="sm" variant={state === "active" ? "secondary" : "primary"} onClick={topUp}>⚡ Top up</Button>
            </div>
          </div>
        )}
      </section>

      <section className={s.right} aria-label="Details">
        <div className={s.head}>
          {c ? (
            <>
              <div className={s.nameRow}>
                <h1 className={s.name}><RansomText key={c.id} text={c.profile.name} size="clamp(44px, 4.4vw, 72px)" slam tone="mixed" /></h1>
              </div>
              <p className={s.meta}>
                {c.profile.age} · {c.profile.pronouns || "—"} · {c.intent === "expert" ? "Expert" : c.intent === "companion" ? "Companion" : "Character"}
                {c.advisory && <Tape tone="paper" size="sm" className={s.advisory}>AI simulation · not professional advice</Tape>}
              </p>
              {c.profile.tagline && <p className={s.tagline}>“{c.profile.tagline}”</p>}
              <div className={s.ctas}>
                {draft ? (
                  <Button variant="primary" size="lg" onClick={() => navigate({ name: "wizard", worldId: route.worldId, characterId: c.id, step: c.creationStep ?? "profile" })}>Continue draft ▸</Button>
                ) : archived ? (
                  <Button variant="primary" size="lg" onClick={() => void restore()}>Restore to roster</Button>
                ) : (
                  <>
                    <Button variant="primary" size="lg" keyLocked={demo} onClick={() => void chat()}>Chat ▸</Button>
                    <Button variant="secondary" onClick={() => navigate({ name: "setup", worldId: route.worldId, cast: [c.id] })}>Add to session ▸</Button>
                  </>
                )}
                {!draft && !archived && <Button variant="ghost" onClick={() => navigate({ name: "wizard", worldId: route.worldId, characterId: c.id, step: "profile", edit: true })}>Edit</Button>}
                {!draft && !archived && !c.isSeed && <Button variant="ghost" onClick={() => void archive()}>Archive</Button>}
              </div>
            </>
          ) : (
            <Skeleton lines={3} widths={["60%", "40%", "80%"]} height={28} />
          )}
        </div>

        <Tabs label="Profile sections" tabs={tabs} value={tab} onChange={setTab} idBase="prf" className={s.tabs} />
        <div className={s.panel} role="tabpanel" id={`prf-panel-${tab}`} aria-labelledby={`prf-tab-${tab}`} key={tab}>
          {!c ? (
            <Skeleton lines={6} />
          ) : tab === "profile" ? (
            <ProfileTabView c={c} />
          ) : tab === "gallery" ? (
            <GalleryTab c={c} onPreview={setPreview} />
          ) : tab === "theme" ? (
            <ThemeTab c={c} song={song ?? null} />
          ) : tab === "sessions" ? (
            <SessionsTab c={c} worldId={route.worldId} onChat={() => void chat()} />
          ) : tab === "memory" ? (
            <MemoryTab c={c} worldId={route.worldId} onChat={() => void chat()} />
          ) : (
            <KnowledgeTab c={c} />
          )}
        </div>
      </section>
    </main>
  );
}
