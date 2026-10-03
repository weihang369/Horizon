// S04 World Hub (WLD-05) + S13 History as its Sessions tab (R13, `?tab=sessions&filter=`).
// Cover header 240 / 168 · tab row 48 with CTAs · roster grid (5 / 4 cols) or session history. Owner: Builder A.
import { openOverlay, toast } from "../../app/layers";
import { audio } from "../../audio/engine";
import { useCharacters, useRushHour, useSessions, useSettings, useWorld } from "../../client/hooks";
import { client } from "../../client";
import type { Route } from "../../router";
import { navigate } from "../../router";
import { Button } from "../../ui/Button";
import { EmptyState } from "../../ui/Panels";
import { RansomText } from "../../ui/RansomText";
import { Tabs, tabIds } from "../../ui/Controls";
import { Tape } from "../../ui/Tape";
import { WorldCover } from "../../ui/WorldCover";
import { BackIcon, PlayIcon, PlusIcon } from "../../ui/icons";
import { useHouseScreen } from "../shell/house";
import { featuredCta, featuredRecording } from "./hubLogic";
import { MoreMenu } from "./MoreMenu";
import { RosterTab } from "./RosterTab";
import { replaySession } from "./sessionActions";
import { SessionsTab } from "./SessionsTab";
import s from "./Hub.module.css";

type HubTab = "roster" | "sessions";
const TAB_BASE = "hub";

export function WorldHubScreen({ route }: { route: Extract<Route, { name: "hub" }> }) {
  useHouseScreen();
  const { worldId } = route;
  const tab: HubTab = route.tab ?? "roster";
  const worldQ = useWorld(worldId);
  const world = worldQ.data;
  const demo = useSettings().data?.demoMode ?? true;
  const charsQ = useCharacters(worldId, { includeArchived: true });
  const sessionsQ = useSessions(worldId);
  const { peak } = useRushHour();
  const chars = charsQ.data ?? [];
  const sessions = sessionsQ.data ?? [];
  const featured = featuredRecording(sessions);
  const approved = chars.filter((c) => c.status === "approved");

  const setTab = (t: HubTab) => {
    if (t === tab) return;
    audio.playSfx("ui_toggle");
    navigate({ name: "hub", worldId, ...(t === "sessions" ? { tab: t } : {}) }, { transition: "none", replace: true });
  };

  if (worldQ.error && !world) {
    return (
      <main className={s.missing} data-screen="S04">
        <EmptyState title="World not found" body="It may have been deleted. Worlds never share characters, so nothing else was affected." action={{ label: "◂ Back to Worlds", run: () => navigate({ name: "worlds" }, { transition: "slash-back" }) }} />
      </main>
    );
  }

  const editWorld = () => openOverlay("O02", { worldId });
  const deleteWorld = () => {
    if (!world) return;
    openOverlay("O03", {
      title: `Delete ${world.name}?`,
      body: `This deletes ${chars.length} character${chars.length === 1 ? "" : "s"} and ${sessions.length} session${sessions.length === 1 ? "" : "s"} in this world. Other worlds are untouched.`,
      typed: world.name,
      confirmLabel: "Delete world",
      onConfirm: async () => {
        await client.worlds.delete(worldId);
        navigate({ name: "worlds" }, { transition: "slash-back" });
        toast({ variant: "info", text: `Deleted ${world.name}.` });
      },
    });
  };

  return (
    <main className={s.hub} data-screen="S04" aria-labelledby="hub-title">
      <header className={s.cover}>
        {world ? <WorldCover cover={world.cover} className={s.coverArt} /> : <div className={`${s.coverArt} ${s.coverLoading}`} />}
        <div className={s.coverShade} aria-hidden="true" />
        <div className={s.coverTop}>
          <Button variant="ghost" size="sm" icon={<BackIcon />} onClick={() => navigate({ name: "worlds" }, { transition: "slash-back" })}>Worlds</Button>
        </div>
        <div className={s.coverMain}>
          <div className={s.titleBlock}>
            {world?.isSeed && <Tape tone="paper" size="sm" className={s.coverTape}>DEMO WORLD</Tape>}
            <h1 id="hub-title" className={s.worldName}>
              {world ? <RansomText text={world.name.toUpperCase()} size="var(--name-size)" tone="mixed" slam delayMs={180} staggerMs={28} /> : <span className={s.nameSkeleton} aria-label="Loading world" />}
            </h1>
            {world?.you && (
              <p className={s.youChip}>
                <span className={s.youTag}>YOU</span>
                <span className={s.youName}>{world.you.displayName}</span>
                {world.you.about && <span className={s.youAbout}>{world.you.about}</span>}
              </p>
            )}
          </div>
          <div className={s.coverActions}>
            {demo && featured && (
              <Button size="lg" icon={<PlayIcon />} className={s.watchCta} onClick={() => { audio.playSfx("ui_confirm"); replaySession(featured); }}>
                {featuredCta(featured)}
              </Button>
            )}
            <MoreMenu
              label="World options"
              items={[
                { id: "edit", label: "Edit world" },
                { id: "history", label: "Session history" },
                { id: "delete", label: "Delete world…", danger: true, divider: true },
              ]}
              onSelect={(id) => (id === "edit" ? editWorld() : id === "delete" ? deleteWorld() : setTab("sessions"))}
            />
          </div>
        </div>
      </header>

      <nav className={s.tabRow} aria-label="World hub">
        <Tabs<HubTab>
          label="Hub sections"
          idBase={TAB_BASE}
          value={tab}
          onChange={setTab}
          className={s.tabs}
          tabs={[
            { id: "roster", label: "Roster", badge: charsQ.loading ? undefined : approved.length },
            { id: "sessions", label: "Sessions", badge: sessionsQ.loading ? undefined : sessions.length },
          ]}
        />
        <div className={s.tabRowRight}>
          {peak && <Tape tone="warn" size="sm" title="DeepSeek peak pricing: replies cost 2× ⚡">RUSH HOUR · replies cost 2× ⚡</Tape>}
          <Button variant="secondary" icon={<PlusIcon />} onClick={() => navigate({ name: "wizard", worldId })}>New Character</Button>
          <Button
            onClick={() => navigate({ name: "setup", worldId })}
            disabled={!charsQ.loading && approved.length === 0}
            title={approved.length === 0 ? "Summon a character first" : undefined}
          >
            Start Session ▸
          </Button>
        </div>
      </nav>

      <section key={tab} className={s.panel} role="tabpanel" id={tabIds(TAB_BASE, tab).panel} aria-labelledby={tabIds(TAB_BASE, tab).tab}>
        {tab === "roster"
          ? <RosterTab worldId={worldId} route={route} chars={chars} loading={charsQ.loading} sessions={sessions} demo={demo} />
          : <SessionsTab worldId={worldId} route={route} chars={chars} sessions={sessions} loading={sessionsQ.loading} demo={demo} featured={featured} />}
      </section>
    </main>
  );
}
