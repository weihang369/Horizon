// SessionScreen (S07/S09/S10/S12 frame, R5). Owner: C.
// Picks layouts[mode] and docks[kind] from the registry; driven by useSessionRuntime(sessionId, { replay }).
// Header: back · title · mode tag · REPLAY tag · (1:1) AUTO|MANUAL · Readable · cost HUD · Log · Insight.
// Mid-session settings arrive as session.state events (D-57), so everything reads the runtime's session fields.
// Single-character sessions theme the app root with the character's palette (R9). Replay opens at route `t`.
import { useEffect, useMemo, useRef, useState } from "react";
import { client } from "../../client";
import { useCharacters, useSessionRuntime, useSettings } from "../../client/hooks";
import { back } from "../../router";
import { closeOverlay, isOverlayOpen, openOverlay, toast } from "../../app/layers";
import { run } from "../../app/errors";
import { useShortcut } from "../../app/shortcuts";
import { emotionForHotkey } from "../../character/emotionMeta";
import type { SessionMode } from "../../contract/types";
import { formatTokens, formatUsd } from "../../domain/format";
import { usePrefs } from "../../stores/prefs";
import { useUi } from "../../stores/ui";
import { setAppPalette } from "../../theme/appPalette";
import { IconButton } from "../../ui/Button";
import { Skeleton } from "../../ui/Data";
import { ErrorTape } from "../../ui/Panels";
import { Tape } from "../../ui/Tape";
import { cx } from "../../ui/cx";
import { BackIcon, InfoIcon, PlayIcon } from "../../ui/icons";
import { Kbd } from "../../ui/Kbd";
import { DockExpansion } from "../ensemble/DockExpansion";
import { setFace } from "./EmotionPicker";
import { retimeBus } from "./ReplayTransport";
import { SpeakerCutIn } from "./SpeakerCutIn";
import { currentSpeakerId, SessionContext, useChars, type SessionCtx } from "./sessionContext";
import { useSessionAudio } from "./useSessionAudio";
import type { SessionRoute } from "./registry";
import { dockFor, docks, layoutOwnsDock, layouts } from "./registry";
import s from "./SessionScreen.module.css";

const MODE_LABEL: Record<SessionMode, string> = { one_on_one: "1:1", group: "Group", debate: "Debate", watch: "Watch" };
const PAUSE_COPY: Record<string, string> = {
  user: "Paused",
  turn_cap: "Paused · turn limit reached",
  daily_budget: "Paused · daily budget reached",
  error: "Paused · something went wrong",
  navigated_away: "Paused when you left",
};

export function SessionScreen({ route }: { route: SessionRoute }) {
  const replay = !!route.replay;
  // Gap-trim toggle rebuilds the replay runtime (it reads the pref at start): release, then re-acquire.
  const [retiming, setRetiming] = useState(false);
  const pendingSeq = useRef<number | null>(null);
  const rtLive = useSessionRuntime(retiming ? null : route.sessionId, { replay });
  const lastRt = useRef(rtLive);
  if (rtLive.session) lastRt.current = rtLive;
  const rt = retiming ? lastRt.current : rtLive;

  const settings = useSettings().data;
  const demo = settings?.demoMode ?? true;
  useCharacters(rt.session?.worldId, { includeArchived: true });
  const chars = useChars();
  const expansion = useUi((u) => u.dockExpansion);
  const insightOpen = useUi((u) => u.layers.some((l) => l.id === "O08"));
  const presenter = usePrefs((p) => p.presenterMode);
  const [readableLocal, setReadableLocal] = useState<boolean | null>(null);

  // Replay deep link `t` (seq) and the retime return point.
  const seeked = useRef(false);
  useEffect(() => {
    if (!replay || rtLive.status !== "ready" || !rtLive.session) return;
    if (pendingSeq.current !== null) {
      const q = pendingSeq.current;
      pendingSeq.current = null;
      if (q > 0) rtLive.controls.seekSeq(q);
      return;
    }
    if (route.t !== undefined && !seeked.current) {
      seeked.current = true;
      rtLive.controls.seekSeq(route.t);
    }
  }, [replay, rtLive.status, rtLive.session, route.t, rtLive.controls]);

  useEffect(() => retimeBus.subscribe((st, prev) => {
    if (st.n === prev.n) return;
    rtLive.controls.pause();
    pendingSeq.current = st.seq;
    setRetiming(true);
    setTimeout(() => setRetiming(false), 380);
  }), [rtLive.controls]);

  const session = rt.session;
  const mode = session?.mode;
  const lead = session?.participants[0] ? chars[session.participants[0].characterId] : undefined;

  // R9: the 1:1 character's palette themes the whole app root (snap on entry; house again on leave).
  const leadPalette = mode === "one_on_one" ? lead?.paletteId ?? null : null;
  useEffect(() => {
    setAppPalette(leadPalette);
  }, [leadPalette]);
  useEffect(() => () => setAppPalette(null), []);

  // Music director + session SFX.
  const speakerId = currentSpeakerId(rt);
  useSessionAudio(rt, chars, speakerId);

  const live = !!session && !replay && !session.isSeed && session.status !== "ended";
  const ctx = useMemo<SessionCtx | null>(() => session ? {
    replay,
    demo,
    isSeed: session.isSeed,
    readable: readableLocal ?? session.readableMode,
    worldId: session.worldId,
    sessionId: session.id,
    insightOpen,
  } : null, [session, replay, demo, readableLocal, insightOpen]);

  // ── Shortcuts (APP-10, doc 03 §6) ──
  const toggleInsight = () => {
    if (!session) return;
    if (isOverlayOpen("O08")) closeOverlay("O08");
    else openOverlay("O08", { sessionId: session.id });
  };
  useShortcut("i", toggleInsight, { when: () => !!session });
  useShortcut("l", () => session && openOverlay("O10", { sessionId: session.id }), { when: () => !!session && !isOverlayOpen("O10") });
  useShortcut("ctrl+.", () => session && void run(() => client.chat.stop(session.id)), { allowInInput: true, when: () => live && !!rt.streamingId });
  for (let k = 1; k <= 7; k++) {
    // eslint-disable-next-line react-hooks/rules-of-hooks -- fixed count, stable order
    useShortcut(`alt+${k}`, () => {
      const e = emotionForHotkey(String(k));
      const cid = session?.participants[0]?.characterId;
      if (e && cid && session) setFace(session.id, cid, e);
    }, { allowInInput: true, when: () => live && mode === "one_on_one" && session?.emotionMode === "user" });
  }

  if (rt.status === "error") {
    return (
      <main className={s.errorScreen}>
        <ErrorTape message={rt.error?.message ?? "This session can't be opened."} code={rt.error?.code} action={{ label: "◂ Back", run: () => back() }} />
      </main>
    );
  }
  if (!session || !ctx) {
    return (
      <main className={cx(s.frame, demo && s.withDemo)} aria-busy="true">
        <header className={s.header}><Skeleton lines={1} widths={["320px"]} height={20} label="Loading session" /></header>
        <div className={s.stageArea}><div className={s.loadingStage} /></div>
      </main>
    );
  }

  const Layout = layouts[session.mode];
  const Dock = docks[dockFor(session.mode, { replay, isSeed: session.isSeed, demo })];
  const dockEl = <Dock rt={rt} sessionId={session.id} worldId={session.worldId} replay={replay} />;
  // The replay transport needs the full width; S07 keeps its inline composer only when live.
  const ownsDock = !!layoutOwnsDock[session.mode] && !replay;
  const push = insightOpen && session.mode === "one_on_one";
  const advisory = session.participants.some((p) => chars[p.characterId]?.advisory);
  const showHud = settings?.cost.showHud ?? true;
  const tokens = rt.list.reduce((n, m) => n + (m.usage ? m.usage.tokensIn + m.usage.tokensOut : 0), 0);
  const readable = ctx.readable;
  const manual = session.emotionMode === "user";
  const streamMsg = rt.streamingId ? rt.messages[rt.streamingId] : undefined;
  const cutSpeaker = streamMsg?.author.characterId ? chars[streamMsg.author.characterId] : undefined;
  const cutPart = session.participants.find((p) => p.characterId === cutSpeaker?.id);
  const paused = rt.paused && !replay && !session.isSeed && session.status !== "ended";

  const setMode = (m: "llm" | "user") => {
    if (m === session.emotionMode) return;
    void run(() => client.chat.setEmotionMode(session.id, m)).then(() => toast({
      variant: "info",
      text: m === "user" ? "MANUAL: you set the face (Alt+1…7). Replies are unchanged." : "AUTO: the AI picks the face for each reply.",
    }));
  };
  const toggleReadable = () => {
    const next = !readable;
    setReadableLocal(next);
    if (live) void run(() => client.chat.setReadableMode(session.id, next));
  };

  return (
    <SessionContext.Provider value={ctx}>
      <main
        className={cx(s.frame, demo && s.withDemo, push && (presenter ? s.pushCompact : s.push))}
        data-screen="session"
        data-mode={session.mode}
        data-replay={replay || undefined}
      >
        <header className={s.header}>
          <IconButton label="Back" size="sm" onClick={() => back()}><BackIcon /></IconButton>
          <h1 className={s.title} title={session.title}>{session.title}</h1>
          <span className={s.modeTag}>{MODE_LABEL[session.mode]}</span>
          {replay && <Tape tone="brand" size="sm" className={s.replayTag}><span className={s.recDot} aria-hidden="true" />Replay</Tape>}
          {!replay && session.isSeed && <Tape tone="paper" size="sm">Recording</Tape>}
          {session.continuedFrom && !replay && <Tape tone="ok" size="sm">Live copy</Tape>}
          <div className={s.tools}>
            {showHud && (
              <span className={s.hud} title="Session cost · tokens">
                {formatUsd(session.costUsd)} · {formatTokens(tokens)}
              </span>
            )}
            {session.mode === "one_on_one" && (
              live ? (
                <div className={s.seg} role="radiogroup" aria-label="Emotion mode">
                  <button type="button" role="radio" aria-checked={!manual} className={cx(s.segBtn, !manual && s.segOn)} onClick={() => setMode("llm")}>Auto</button>
                  <button type="button" role="radio" aria-checked={manual} className={cx(s.segBtn, manual && s.segOn)} onClick={() => setMode("user")}>Manual</button>
                </div>
              ) : (
                <span className={s.modeStatic}>Face · {manual ? "Manual" : "Auto"}</span>
              )
            )}
            {(session.mode === "one_on_one" || session.mode === "group") && (
              <button type="button" className={cx(s.toolBtn, readable && s.toolOn)} aria-pressed={readable} onClick={toggleReadable}>Readable</button>
            )}
            <button type="button" className={s.toolBtn} onClick={() => openOverlay("O10", { sessionId: session.id })} title="Backlog (L)">Log</button>
            <button type="button" className={cx(s.insightBtn, insightOpen && s.insightOn)} aria-pressed={insightOpen} onClick={toggleInsight} title="Insight (I)">
              <span className={s.insightShape} aria-hidden="true" />
              <span className={s.insightContent}><InfoIcon width={15} height={15} />Insight</span>
            </button>
          </div>
        </header>
        {(advisory || paused) && (
          <div className={s.tapes}>
            {advisory && <span className={s.sme}>AI simulation · not professional advice</span>}
            {paused && (
              <span className={s.pausedTape}>
                {PAUSE_COPY[rt.pausedReason ?? "user"] ?? "Paused"}
                {session.mode === "one_on_one" && rt.pausedReason === "navigated_away" ? " · send a message to pick it back up" : ""}
              </span>
            )}
          </div>
        )}
        <div className={s.stageArea}>
          <Layout rt={rt} route={route} replay={replay} dock={ownsDock ? dockEl : undefined} insightOpen={insightOpen} />
          {session.mode !== "one_on_one" && (
            <SpeakerCutIn
              speaker={cutSpeaker}
              emotion={cutPart ? rt.participants.find((p) => p.characterId === cutPart.characterId)?.displayEmotion ?? "neutral" : "neutral"}
              side={cutPart?.side}
              messageId={rt.streamingId}
              suppress={retiming}
            />
          )}
          {retiming && <div className={s.retime}><Tape tone="ink" size="sm">Re-timing replay…</Tape></div>}
          {replay && !retiming && route.t === undefined && rt.player && !rt.player.playing && !rt.player.ended && rt.player.position < 200 && (
            // U1: a replay opens paused on an empty stage; give first-time viewers one obvious way in.
            <div className={s.watch}>
              <button type="button" className={s.watchBtn} onClick={() => rt.controls.play()} tabIndex={-1}>
                <span className={s.watchShape} aria-hidden="true" />
                <PlayIcon width={30} height={30} />
                <span>Watch</span>
                <span className={s.watchKey}><Kbd>Space</Kbd></span>
              </button>
            </div>
          )}
        </div>
        {!ownsDock && (
          <div className={cx(s.dock, insightOpen && !push && (presenter ? s.dockUnderCompact : s.dockUnder))}>
            {expansion?.sessionId === session.id && <DockExpansion {...expansion} layerKey={0} close={() => closeOverlay("O12")} />}
            {dockEl}
          </div>
        )}
      </main>
    </SessionContext.Provider>
  );
}
