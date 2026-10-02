// S08 Session Setup (MULTI-01/05/09) — Builder D. Mode → Cast → Config, each step addressable
// (#/w/:wid/setup/:step?mode=&cast=). Start ▸ creates the session and plays the mode intro: Group = wings slide in,
// Debate = VS splash (O16 on the first round), Watch = curtain slash. Live actions need a key (R15 → O05).
import { useEffect, useMemo, useState } from "react";
import type { CSSProperties, DragEvent } from "react";
import { useStore } from "zustand";
import { client } from "../../client";
import { useCharacters, useSettings, useWorld } from "../../client/hooks";
import type { Character, DebateConfig, GroupConfig, MusicPolicy, Side, WatchConfig } from "../../contract/types";
import { reportError } from "../../app/errors";
import { openOverlay } from "../../app/layers";
import { useShortcut } from "../../app/shortcuts";
import { EnergyBar, PortraitCard } from "../../character";
import type { Route } from "../../router";
import { back, navigate } from "../../router";
import { sessionStore } from "../../stores/session";
import { PaletteScope } from "../../theme";
import { Button, EmptyState, RansomText, Segmented, Select, Skeleton, Tape, TextArea, TextField, Toggle, cx } from "../../ui";
import { PACE_OPTIONS, firstName } from "./shared";
import { autoAssign, castLimits, estimateRoundSec, suggestMotions } from "./setupLogic";
import s from "./SetupScreen.module.css";

type SetupRoute = Extract<Route, { name: "setup" }>;
type Mode = NonNullable<SetupRoute["mode"]>;
type Step = NonNullable<SetupRoute["step"]>;

const MODES: { id: Mode; title: string; line: string; tag: string }[] = [
  { id: "group", title: "GROUP CHAT", line: "Talk with up to five of them at once. They answer each other too.", tag: "2–5 · you talk" },
  { id: "debate", title: "DEBATE", line: "Two sides, one motion, real rounds. You moderate; an arbiter judges.", tag: "2–5 · you steer" },
  { id: "watch", title: "WATCH", line: "Set the scene and sit back. They play it out among themselves.", tag: "2–5 · you direct" },
];
const STEPS: { id: Step; label: string }[] = [
  { id: "mode", label: "Mode" },
  { id: "cast", label: "Cast" },
  { id: "config", label: "Setup" },
];

export function SetupScreen({ route }: { route: SetupRoute }) {
  const worldId = route.worldId;
  const world = useWorld(worldId).data;
  const charsQ = useCharacters(worldId);
  const demo = useSettings().data?.demoMode ?? true;
  const roster = useMemo(() => (charsQ.data ?? []).filter((c) => c.status === "approved"), [charsQ.data]);
  const mode = route.mode;
  const step: Step = !mode ? "mode" : route.step === "config" && (route.cast?.length ?? 0) >= 2 ? "config" : route.step === "mode" ? "mode" : route.step ?? "cast";
  const cast = useMemo(() => (route.cast ?? []).filter((id) => roster.some((c) => c.id === id) || !charsQ.data), [route.cast, roster, charsQ.data]);
  const byId = useMemo(() => Object.fromEntries(roster.map((c) => [c.id, c])), [roster]);

  const go = (patch: Partial<SetupRoute>, replace = false) =>
    navigate({ name: "setup", worldId, step, mode, cast: route.cast, ...patch }, { transition: "none", replace });

  // ── Config state (kept while you move between steps) ──
  const [title, setTitle] = useState("");
  const [faces, setFaces] = useState<"llm" | "user">("llm");
  const [responders, setResponders] = useState<GroupConfig["responderPolicy"]>("auto");
  const [music, setMusic] = useState<MusicPolicy>("follow_speaker");
  const [motion, setMotion] = useState("");
  const [format, setFormat] = useState<DebateConfig["format"]>("two_sided");
  const [sides, setSides] = useState<Record<string, Side>>({});
  const [rounds, setRounds] = useState<DebateConfig["roundsPreset"]>("standard");
  const [turnLength, setTurnLength] = useState<DebateConfig["turnLength"] | null>(null);
  const [moderator, setModerator] = useState<DebateConfig["moderator"]>("user");
  const [verdictBy, setVerdictBy] = useState<DebateConfig["verdictBy"]>("arbiter");
  const [premise, setPremise] = useState("");
  const [length, setLength] = useState<WatchConfig["maxTurns"]>(20);
  const [pace, setPace] = useState<WatchConfig["paceMs"]>(1500);
  const [opener, setOpener] = useState<string>("auto");
  const [advanced, setAdvanced] = useState((route.cast?.length ?? 0) >= 5);
  const [starting, setStarting] = useState(false);

  // Keep sides in sync with the cast (new picks auto-assigned, dropped picks removed).
  useEffect(() => {
    setSides((cur) => autoAssign(cast, cur));
  }, [cast.join(",")]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (format === "panel" && verdictBy === "user") setVerdictBy("arbiter");
  }, [format, verdictBy]);

  const limits = castLimits(advanced);
  const toggleCast = (id: string) => {
    const has = cast.includes(id);
    const next = has ? cast.filter((x) => x !== id) : cast.length < limits.max ? [...cast, id] : cast;
    go({ cast: next, step: "cast" }, true);
  };

  const propN = cast.filter((id) => sides[id] === "prop").length;
  const oppN = cast.filter((id) => sides[id] === "opp").length;
  const configOk =
    mode === "group" ? true
      : mode === "debate" ? motion.trim().length > 0 && motion.length <= 200 && (format === "panel" || (propN >= 1 && oppN >= 1))
        : mode === "watch" ? premise.trim().length > 0 && premise.length <= 300 : false;
  const castOk = cast.length >= limits.min && cast.length <= limits.max;

  const doCreate = async () => {
    if (!mode) return;
    setStarting(true);
    try {
      const config =
        mode === "group" ? ({ responderPolicy: responders, maxAutoResponders: 2 } satisfies Partial<GroupConfig>)
          : mode === "debate" ? ({
            motion: motion.trim(), format,
            ...(format === "two_sided" ? { sides: { prop: cast.filter((id) => sides[id] === "prop"), opp: cast.filter((id) => sides[id] === "opp") } } : {}),
            roundsPreset: rounds, phases: rounds === "quick" ? ["opening", "closing"] : ["opening", "rebuttal", "closing"],
            turnLength: turnLength ?? (cast.length >= 5 ? "short" : "medium"), moderator, verdictBy,
            rubric: [{ id: "evidence", label: "Evidence" }, { id: "rebuttal", label: "Rebuttal" }, { id: "clarity", label: "Clarity" }, { id: "persuasion", label: "Persuasion" }],
            autoAdvance: true, pauseMs: 1500,
          } satisfies DebateConfig)
            : ({ premise: premise.trim(), maxTurns: length, paceMs: pace, openingSpeaker: opener } satisfies WatchConfig);
      const snap = await client.sessions.create({
        worldId, mode, characterIds: cast, title: title.trim() || undefined, emotionMode: faces,
        musicPolicy: mode === "debate" ? "arena" : music, config,
        ...(mode === "debate" && format === "two_sided" ? { sides } : {}),
      });
      navigate({ name: "session", worldId, sessionId: snap.session.id }, { transition: mode === "group" ? "fade" : "slash" });
    } catch (err) {
      reportError(err, { context: "Starting a session needs an OpenRouter key." });
      setStarting(false);
    }
  };

  // MULTI-01 AC4: one streaming session at a time.
  const streamingElsewhere = useStore(sessionStore, (st) => Object.values(st.slots).find((x) => !x.replay && (x.runtime?.streamingId || x.runtime?.thinkingId)));
  const start = () => {
    if (!configOk || !castOk || starting) return;
    const other = streamingElsewhere?.runtime?.session;
    if (other) {
      openOverlay("O03", {
        title: `Pause “${other.title}” and continue?`,
        body: "Only one session streams at a time. It will wait for you, paused.",
        confirmLabel: "Pause it & start",
        onConfirm: async () => {
          await client.sessions.leave(other.id).catch(() => {});
          await doCreate();
        },
      });
      return;
    }
    void doCreate();
  };
  useShortcut("ctrl+enter", start, { allowInInput: true, when: () => step === "config" });

  const stepIdx = STEPS.findIndex((x) => x.id === step);
  const modeMeta = MODES.find((m) => m.id === mode);

  return (
    <main className={s.root} data-screen="setup">
      <header className={s.head}>
        <Button variant="ghost" size="sm" onClick={() => back()}>◂ {world?.name ?? "Back"}</Button>
        <RansomText as="h1" text="NEW SESSION" size={40} tone="mixed" className={s.title} />
        <ol className={s.rail} aria-label="Setup steps">
          {STEPS.map((x, i) => (
            <li key={x.id}>
              <button
                type="button"
                className={s.railStep}
                data-state={i < stepIdx ? "done" : i === stepIdx ? "current" : "todo"}
                aria-current={i === stepIdx ? "step" : undefined}
                disabled={(x.id !== "mode" && !mode) || (x.id === "config" && !castOk)}
                onClick={() => go({ step: x.id })}
              >
                <span className={s.railNo}>{i + 1}</span>
                {x.id === "config" && modeMeta ? `${modeMeta.title.split(" ")[0]} setup` : x.label}
              </button>
            </li>
          ))}
        </ol>
      </header>

      <section className={s.body} key={step}>
        {step === "mode" && (
          <div className={s.modes} role="radiogroup" aria-label="Session mode">
            {MODES.map((m, i) => (
              <button
                key={m.id}
                type="button"
                role="radio"
                aria-checked={mode === m.id}
                className={cx(s.modeCard, s[`mode_${m.id}`], mode === m.id && s.modeOn)}
                style={{ "--i": i } as CSSProperties}
                onClick={() => go({ mode: m.id, step: "cast" })}
              >
                <span className={s.preview} aria-hidden="true"><ModePreview mode={m.id} /></span>
                <span className={s.modeTitle}>{m.title}</span>
                <span className={s.modeLine}>{m.line}</span>
                <span className={s.modeTag}>{m.tag}</span>
              </button>
            ))}
          </div>
        )}

        {step === "cast" && (
          <div className={s.castStep}>
            <div className={s.castHead}>
              <h2 className={s.h2}>Pick the cast <span>{cast.length} / {limits.max}</span></h2>
              <p className={s.hint}>
                {limits.min}–{limits.max} characters from {world?.name ?? "this world"}. Each reply takes a few seconds:
                {" "}a full round of {Math.max(cast.length, 2)} is about <b>{estimateRoundSec(Math.max(cast.length, 2), mode ?? "group")} s</b>.
              </p>
              <Toggle checked={advanced} onChange={(v) => { setAdvanced(v); if (!v && cast.length > 4) go({ cast: cast.slice(0, 4) }, true); }} label="Advanced · 5th seat" />
            </div>
            {charsQ.loading ? (
              <div className={s.castGrid}>{Array.from({ length: 5 }, (_, i) => <Skeleton key={i} height={260} />)}</div>
            ) : roster.length < 2 ? (
              <EmptyState title="Not enough characters" body="A multi-character session needs at least two approved characters in this world." action={{ label: "+ New Character", run: () => navigate({ name: "wizard", worldId }) }} />
            ) : (
              <div className={s.castGrid} role="group" aria-label="Cast">
                {roster.map((c) => {
                  const idx = cast.indexOf(c.id);
                  const on = idx >= 0;
                  const full = !on && cast.length >= limits.max;
                  return (
                    <PaletteScope key={c.id} paletteId={c.paletteId} className={s.castCellWrap}>
                      <button
                        type="button"
                        aria-pressed={on}
                        disabled={full}
                        className={cx(s.castCell, on && s.castOn)}
                        onClick={() => toggleCast(c.id)}
                        title={full ? `Max ${limits.max}${advanced ? "" : " (turn on Advanced for a 5th seat)"}` : undefined}
                      >
                        <PortraitCard character={c} emotion={on ? "happy" : "neutral"} size="card" width="100%" parallax={false} />
                        {on && <span className={s.castNo}>{idx + 1}</span>}
                        <span className={s.castName}>{firstName(c)}</span>
                        <span className={s.castRole}>{c.profile.role}</span>
                        <EnergyBar characterId={c.id} size="stage" label={c.profile.name} className={s.castEnergy} />
                      </button>
                    </PaletteScope>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {step === "config" && mode && (
          <div className={s.config}>
            <aside className={s.castStrip} aria-label="Your cast">
              <Tape tone="ink" size="sm">{modeMeta?.title}</Tape>
              <div className={s.stripCards}>
                {cast.map((id) => byId[id] && <PortraitCard key={id} character={byId[id]} emotion="neutral" size="thumb" width={64} />)}
              </div>
              <Button variant="ghost" size="sm" onClick={() => go({ step: "cast" })}>Change cast</Button>
            </aside>
            <div className={s.form}>
              {mode === "debate" && (
                <>
                  <div className={s.field2}>
                    <TextArea label="Motion" value={motion} maxLength={200} counter rows={2} placeholder="This house would…" onChange={(e) => setMotion(e.target.value)} />
                    <div className={s.suggest}>
                      <span className={s.lbl}>Suggest</span>
                      {suggestMotions(world?.name).map((m) => (
                        <button key={m} type="button" className={s.suggestChip} onClick={() => setMotion(m)}>{m}</button>
                      ))}
                    </div>
                  </div>
                  <Row label="Format">
                    <Segmented label="Format" value={format} onChange={setFormat} options={[{ value: "two_sided", label: "Two sides" }, { value: "panel", label: "Panel" }]} />
                    <span className={s.note}>{format === "panel" ? "Each argues their own position · summary verdict, no winner." : "Proposition vs Opposition. Uneven sides are fine."}</span>
                  </Row>
                  {format === "two_sided" && <SidesBoard cast={cast} byId={byId} sides={sides} setSides={setSides} />}
                  <Row label="Rounds">
                    <Segmented label="Rounds" value={rounds} onChange={setRounds} options={[{ value: "quick", label: "Quick" }, { value: "standard", label: "Standard" }]} />
                    <span className={s.note}>{rounds === "quick" ? "Opening → Closing" : "Opening → Rebuttal → Closing"}</span>
                  </Row>
                  <Row label="Turn length">
                    <Segmented
                      label="Turn length"
                      value={turnLength ?? (cast.length >= 5 ? "short" : "medium")}
                      onChange={setTurnLength}
                      options={[{ value: "short", label: "Short ≈80" }, { value: "medium", label: "Medium ≈150" }, { value: "long", label: "Long ≈250" }]}
                    />
                  </Row>
                  <Row label="Moderator">
                    <Segmented label="Moderator" value={moderator} onChange={setModerator} options={[{ value: "user", label: "You" }, { value: "auto_host", label: "Auto host" }]} />
                  </Row>
                  <Row label="Verdict by">
                    <Segmented
                      label="Verdict by"
                      value={verdictBy}
                      onChange={setVerdictBy}
                      options={format === "panel"
                        ? [{ value: "arbiter", label: "Arbiter summary" }, { value: "none", label: "None" }]
                        : [{ value: "arbiter", label: "Arbiter (AI)" }, { value: "user", label: "You decide" }, { value: "none", label: "None" }]}
                    />
                  </Row>
                </>
              )}
              {mode === "watch" && (
                <>
                  <TextArea label="Premise / scene" value={premise} maxLength={300} counter rows={3} placeholder="Rainy Sunday. One of them wants to go out; the other is mid-raid." onChange={(e) => setPremise(e.target.value)} />
                  <Row label="Length">
                    <Segmented label="Length" value={String(length)} onChange={(v) => setLength(Number(v) as WatchConfig["maxTurns"])} options={[{ value: "10", label: "10 turns" }, { value: "20", label: "20 turns" }, { value: "40", label: "40 turns" }]} />
                  </Row>
                  <Row label="Pace">
                    <Segmented label="Pace" value={String(pace)} onChange={(v) => setPace(Number(v) as WatchConfig["paceMs"])} options={PACE_OPTIONS.map((o) => ({ value: o.value, label: o.label }))} />
                    <span className={s.note}>{pace === 3000 ? "3 s" : pace === 1500 ? "1.5 s" : "0.5 s"} between turns</span>
                  </Row>
                  <Row label="Opening speaker">
                    <Select label="Opening speaker" hideLabel value={opener} onChange={setOpener} options={[{ value: "auto", label: "Auto" }, ...cast.map((id) => ({ value: id, label: byId[id]?.profile.name ?? id }))]} />
                  </Row>
                </>
              )}
              {mode === "group" && (
                <Row label="Who responds">
                  <Segmented label="Who responds" value={responders} onChange={setResponders} options={[{ value: "auto", label: "Auto (≤2)" }, { value: "everyone", label: "Everyone" }, { value: "mentioned", label: "Mentioned only" }]} />
                </Row>
              )}
              {mode !== "debate" && (
                <Row label="Music">
                  <Segmented label="Music" value={music === "scene_bed" ? "scene_bed" : "follow_speaker"} onChange={setMusic} options={[{ value: "follow_speaker", label: "Follow speaker" }, { value: "scene_bed", label: "Scene bed" }]} />
                </Row>
              )}
              <Row label="Faces">
                <Segmented label="Faces" value={faces} onChange={setFaces} options={[{ value: "llm", label: "AUTO" }, { value: "user", label: "MANUAL" }]} />
                <span className={s.note}>{faces === "user" ? "You set faces from the portrait menu; reactions off." : "Faces follow what they say; listeners react."}</span>
              </Row>
              <TextField label="Title (optional)" value={title} maxLength={80} placeholder={mode === "debate" && motion ? `Debate: ${motion.slice(0, 40)}` : "Auto"} onChange={(e) => setTitle(e.target.value)} />
            </div>
          </div>
        )}
      </section>

      <footer className={s.bar}>
        <span className={s.barInfo}>
          {mode ? <>{modeMeta?.title} · {cast.length} cast{step === "config" && mode === "debate" && format === "two_sided" ? ` · ${propN} v ${oppN}` : ""}</> : "Choose how they'll talk"}
        </span>
        <Button variant="ghost" onClick={() => (stepIdx > 0 ? go({ step: STEPS[stepIdx - 1].id }) : back())}>◂ Back</Button>
        {step === "cast" && (
          <Button disabled={!castOk} onClick={() => go({ step: "config" })}>Next ▸</Button>
        )}
        {step === "config" && (
          <Button size="lg" disabled={!configOk || !castOk || starting} keyLocked={demo} onClick={start}>
            {starting ? "Starting…" : "Start ▸"}
          </Button>
        )}
      </footer>
    </main>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className={s.row}>
      <span className={s.lbl}>{label}</span>
      <div className={s.rowBody}>{children}</div>
    </div>
  );
}

function SidesBoard({ cast, byId, sides, setSides }: { cast: string[]; byId: Record<string, Character>; sides: Record<string, Side>; setSides: (f: (s: Record<string, Side>) => Record<string, Side>) => void }) {
  const [over, setOver] = useState<Side | null>(null);
  const drop = (side: Side) => (e: DragEvent) => {
    e.preventDefault();
    const id = e.dataTransfer.getData("text/plain");
    if (id) setSides((cur) => ({ ...cur, [id]: side }));
    setOver(null);
  };
  const col = (side: Side) => (
    <div
      className={cx(s.sideCol, s[`side_${side}`], over === side && s.sideOver)}
      onDragOver={(e) => { e.preventDefault(); setOver(side); }}
      onDragLeave={() => setOver(null)}
      onDrop={drop(side)}
      aria-label={side === "prop" ? "Proposition" : "Opposition"}
      role="group"
    >
      <Tape tone={side} size="sm">{side === "prop" ? "Proposition" : "Opposition"}</Tape>
      <div className={s.sideChips}>
        {cast.filter((id) => sides[id] === side).map((id) => {
          const c = byId[id];
          if (!c) return null;
          return (
            <PaletteScope key={id} paletteId={c.paletteId} as="span" style={{ display: "contents" }}>
              <button
                type="button"
                draggable
                className={s.sideChip}
                onDragStart={(e) => e.dataTransfer.setData("text/plain", id)}
                onClick={() => setSides((cur) => ({ ...cur, [id]: side === "prop" ? "opp" : "prop" }))}
                title="Drag, or click to switch sides"
                aria-label={`${c.profile.name}, ${side === "prop" ? "Proposition" : "Opposition"}. Activate to switch sides.`}
              >
                <PortraitCard character={c} emotion="neutral" size="head" width={34} />
                {firstName(c)}
                <span aria-hidden="true">⇄</span>
              </button>
            </PaletteScope>
          );
        })}
        {cast.every((id) => sides[id] !== side) && <span className={s.sideEmpty}>Drop a debater here</span>}
      </div>
    </div>
  );
  return (
    <div className={s.sides}>
      {col("prop")}
      <div className={s.sidesMid}>
        <span className={s.vs}>VS</span>
        <Button variant="ghost" size="sm" onClick={() => setSides(() => autoAssign(cast, {}))}>Auto-assign</Button>
      </div>
      {col("opp")}
    </div>
  );
}

function ModePreview({ mode }: { mode: Mode }) {
  if (mode === "debate") {
    return (
      <span className={s.pvDebate}>
        <i /><i /><b>VS</b><i />
      </span>
    );
  }
  if (mode === "watch") {
    return (
      <span className={s.pvWatch}>
        <em /><i /><i /><i /><em />
      </span>
    );
  }
  return (
    <span className={s.pvGroup}>
      <i /><i /><u /><i /><i />
    </span>
  );
}
