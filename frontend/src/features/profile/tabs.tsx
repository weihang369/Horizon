// S06 tab panels: Profile · Gallery · Theme · Sessions · Memory · Knowledge (PRF-01..08). Owner: Builder B.
import { useState } from "react";
import type { CSSProperties } from "react";
import { openOverlay, toast } from "@/app/layers";
import { reportError } from "@/app/errors";
import { client } from "@/client";
import { useJob, useKnowledge, useMemory, useNow, useSessions } from "@/client/hooks";
import type { Character, Emotion, MemoryItem, Session, ThemeSong } from "@/contract/types";
import { EMOTIONS } from "@/contract/types";
import { emotionMeta } from "@/character";
import { formatRelative } from "@/domain/format";
import { navigate } from "@/router";
import { Button, EmptyState, ErrorTape, HalftoneDevelop, Skeleton, Tape } from "@/ui";
import { cx } from "@/ui/cx";
import { isRunning, startGeneration, useCharacterJobs, useEstimate } from "@/features/wizard/generate";
import { useAssetCompareWatcher } from "./compare";
import { Composing, ThemePlayer } from "./ThemePlayer";
import s from "./profile.module.css";

// ── Profile ─────────────────────────────────────────────────────────────────
export function ProfileTabView({ c }: { c: Character }) {
  const p = c.profile;
  const st = p.speakingStyle;
  return (
    <div className={s.prof}>
      <article className={cx(s.card, s.cardWide)}>
        <h3 className={s.cardTitle}>Personality</h3>
        <p className={s.body}>{p.personality.summary || "—"}</p>
        <div className={s.chips}>{p.personality.traits.map((t) => <span key={t} className={s.chip}>{t}</span>)}</div>
      </article>
      {p.backstory && (
        <article className={cx(s.card, s.cardWide)}>
          <h3 className={s.cardTitle}>Backstory</h3>
          <p className={s.body}>{p.backstory}</p>
        </article>
      )}
      <article className={s.card}>
        <h3 className={s.cardTitle}>Voice</h3>
        <p className={s.body}>{st.summary || "—"}</p>
        <p className={s.small}>Tone {st.tone || "—"} · {st.formality}</p>
        {st.quirks.length > 0 && <div className={s.chips}>{st.quirks.map((q) => <span key={q} className={s.chip}>{q}</span>)}</div>}
        {st.catchphrases.length > 0 && <p className={s.quote}>{st.catchphrases.map((x) => `“${x}”`).join("  ")}</p>}
      </article>
      <article className={s.card}>
        <h3 className={s.cardTitle}>Greeting</h3>
        <p className={s.quote}>“{p.greeting || "…"}”</p>
        {p.relationshipToUser && <p className={s.small}>Relationship to you: <b>{p.relationshipToUser}</b></p>}
      </article>
      <article className={s.card}>
        <h3 className={s.cardTitle}>Expertise</h3>
        <div className={s.chips}>{p.expertise.length ? p.expertise.map((x) => <span key={x} className={s.chip}>{x}</span>) : <span className={s.small}>—</span>}</div>
        {p.goals && <p className={s.body}><b className={s.label}>Goals</b> {p.goals}</p>}
      </article>
      <article className={s.card}>
        <h3 className={s.cardTitle}>Boundaries</h3>
        <ul className={s.list}>{p.boundaries.map((b) => <li key={b}>{b}</li>)}</ul>
        {p.exampleLines && p.exampleLines.length > 0 && (
          <>
            <h3 className={s.cardTitle}>Example lines</h3>
            <ul className={s.list}>{p.exampleLines.map((b) => <li key={b}>“{b}”</li>)}</ul>
          </>
        )}
      </article>
    </div>
  );
}

// ── Gallery ─────────────────────────────────────────────────────────────────
export function GalleryTab({ c, onPreview }: { c: Character; onPreview: (e: Emotion | null) => void }) {
  const jobs = useCharacterJobs(c.id);
  const regen = useJob(jobs.emotion_regenerate).data;
  const set = useJob(jobs.emotion_set).data;
  useAssetCompareWatcher(c, jobs.emotion_regenerate);
  const est = useEstimate({ characterId: c.id, kind: "emotion_regenerate", emotions: ["surprised"] });
  const busy = (e: Emotion) => [regen, set].some((j) => isRunning(j) && j!.tasks.some((t) => t.emotion === e && (t.status === "running" || t.status === "queued")));
  const ready = EMOTIONS.filter((e) => !!c.emotions[e]).length;
  return (
    <div className={s.galleryWrap}>
      <p className={s.small}>{ready}/7 faces · hover to preview on the portrait · click to open</p>
      <div className={s.gallery} onMouseLeave={() => onPreview(null)}>
        {EMOTIONS.map((e, i) => {
          const ref = c.emotions[e];
          const m = emotionMeta[e];
          const working = busy(e);
          return (
            <div key={e} className={cx(s.gTile, !ref && s.gMissing)} style={{ "--i": i } as CSSProperties}>
              <button
                type="button"
                className={s.gArt}
                onMouseEnter={() => onPreview(e)}
                onFocus={() => onPreview(e)}
                onBlur={() => onPreview(null)}
                onClick={() => openOverlay("O06", { characterId: c.id, emotion: e })}
                aria-label={`${m.label}${ref ? "" : " (missing)"}: open lightbox`}
              >
                {ref && <img src={ref.url} alt="" draggable={false} />}
                {!ref && !working && <span className={s.gGlyph} aria-hidden="true">{m.icon}</span>}
                {working && <HalftoneDevelop className={s.gDev} label="PAINTING" />}
              </button>
              <div className={s.gFoot}>
                <span className={s.gKey}>{m.hotkey}</span>
                <span className={s.gName}>{m.label}</span>
              </div>
              {!ref && !working && c.status !== "archived" && (
                <button type="button" className={s.gGen} onClick={() => void startGeneration({ characterId: c.id, kind: "emotion_regenerate", emotions: [e] }, `Generate ${m.label.toLowerCase()}`)}>
                  Generate{est ? ` (≈ $${est.toFixed(2)})` : ""}
                </button>
              )}
            </div>
          );
        })}
      </div>
      <p className={s.small}>Missing faces fall back to neutral + VFX in sessions. Regenerating an approved face opens an Old | New choice.</p>
    </div>
  );
}

// ── Theme ───────────────────────────────────────────────────────────────────
export function ThemeTab({ c, song }: { c: Character; song: ThemeSong | null }) {
  const jobs = useCharacterJobs(c.id);
  const job = useJob(jobs.song).data;
  const est = useEstimate({ characterId: c.id, kind: "song" });
  const composing = isRunning(job);
  const failed = !composing && (job?.status === "failed" || song?.status === "failed");
  const compose = () => void startGeneration({ characterId: c.id, kind: "song", ...(song?.brief ? { brief: song.brief } : {}) }, song?.status === "ready" ? "Regenerate theme" : "Compose theme");
  return (
    <div className={s.theme}>
      {composing && job ? <Composing progress={job.progress} /> : song?.status === "ready" ? <ThemePlayer song={song} characterName={c.profile.name} /> : (
        <div className={s.themeNone}><span aria-hidden="true">♪</span><p>No theme yet. The ambient bed plays for {c.profile.name.split(" ")[0]} until one is composed.</p></div>
      )}
      {failed && <ErrorTape message="The composer stalled." action={{ label: "Retry", run: compose, cost: est ?? undefined }} />}
      {song?.brief && (
        <div className={s.card}>
          <h3 className={s.cardTitle}>Song brief</h3>
          <dl className={s.briefList}>
            <div><dt>Genre</dt><dd>{song.brief.genres.join(", ")}</dd></div>
            <div><dt>Mood</dt><dd>{song.brief.moods.join(", ")}</dd></div>
            <div><dt>Tempo</dt><dd>{song.brief.bpm} BPM</dd></div>
            <div><dt>Instruments</dt><dd>{song.brief.instruments.join(", ")}</dd></div>
            <div className={s.briefWide}><dt>Vibe</dt><dd>{song.brief.vibe}</dd></div>
          </dl>
        </div>
      )}
      <div className={s.themeActions}>
        <Button variant="secondary" cost={est ?? undefined} disabled={composing || c.status === "archived"} onClick={compose}>
          {song?.status === "ready" ? "↻ Regenerate (replaces)" : "Compose ▸"}
        </Button>
        <span className={s.small}>One theme per character. Regenerating replaces it; there is no history.</span>
      </div>
      <p className={s.fine}>Model {song?.generation?.model ?? "google/lyria-3-clip"} · {song?.licenseNote ?? "Placeholder: procedural WebAudio sketch (D-52)."}</p>
    </div>
  );
}

// ── Sessions ────────────────────────────────────────────────────────────────
const MODE: Record<Session["mode"], string> = { one_on_one: "1:1", group: "Group", debate: "Debate", watch: "Watch" };

export function SessionsTab({ c, worldId, onChat }: { c: Character; worldId: string; onChat: () => void }) {
  const q = useSessions(worldId);
  const now = useNow(60_000);
  if (q.loading) return <Skeleton lines={4} height={44} />;
  const list = (q.data ?? []).filter((x) => x.participants.some((p) => p.characterId === c.id)).sort((a, b) => (b.lastMessageAt ?? b.updatedAt).localeCompare(a.lastMessageAt ?? a.updatedAt));
  if (!list.length) {
    return <EmptyState title={`${c.profile.name.split(" ")[0]} hasn't joined any conversations yet.`} action={{ label: "Chat", run: onChat }} paletteId={c.paletteId} />;
  }
  return (
    <ul className={s.rows}>
      {list.map((x, i) => (
        <li key={x.id} style={{ "--i": i } as CSSProperties}>
          <button type="button" className={s.row} onClick={() => navigate({ name: "session", worldId, sessionId: x.id, ...(x.isSeed ? { replay: true } : {}) })}>
            <span className={cx(s.mode, s[`mode_${x.mode}`])}>{MODE[x.mode]}</span>
            <span className={s.rowTitle}>{x.title}</span>
            {x.isSeed && <Tape tone="ink" size="sm">Recording</Tape>}
            <span className={s.rowMeta}>{x.messageCount} msgs · {formatRelative(x.lastMessageAt ?? x.updatedAt, now)}</span>
            <span className={s.rowGo} aria-hidden="true">{x.isSeed ? "▶" : "▸"}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}

// ── Memory (Should; mock with ribbon) ───────────────────────────────────────
const KIND: Record<MemoryItem["kind"], string> = { fact: "Fact", event: "Event", preference: "Preference", about_user: "About you" };

export function MemoryTab({ c, worldId, onChat }: { c: Character; worldId: string; onChat: () => void }) {
  const q = useMemory(c.id);
  const now = useNow(60_000);
  const [gone, setGone] = useState<Set<string>>(new Set());
  const forget = async (m: MemoryItem) => {
    setGone((g) => new Set(g).add(m.id));
    try {
      await client.characters.forgetMemory(m.id);
      toast({ variant: "info", text: `${c.profile.name.split(" ")[0]} forgot: “${m.text.slice(0, 40)}${m.text.length > 40 ? "…" : ""}”` });
    } catch (err) {
      setGone((g) => { const n = new Set(g); n.delete(m.id); return n; });
      reportError(err);
    }
  };
  const items = (q.data ?? []).filter((m) => !gone.has(m.id));
  return (
    <div className={s.mem}>
      <div className={s.ribbon}>Preview: final design by AI team</div>
      {q.loading ? <Skeleton lines={4} height={40} /> : items.length === 0 ? (
        <EmptyState title={`Nothing remembered yet. Talk to ${c.profile.name.split(" ")[0]}.`} action={{ label: "Chat", run: onChat }} paletteId={c.paletteId} />
      ) : (
        <ul className={s.memList}>
          {items.map((m, i) => (
            <li key={m.id} className={s.memItem} style={{ "--i": i } as CSSProperties}>
              <span className={s.memKind}>{KIND[m.kind]}</span>
              <p className={s.memText}>{m.text}</p>
              <span className={s.memImp} title={`Importance ${m.importance.toFixed(2)}`} aria-label={`Importance ${Math.round(m.importance * 100)} %`}>
                {[0.25, 0.5, 0.75].map((t) => <i key={t} className={cx(m.importance >= t && s.on)} />)}
              </span>
              <span className={s.memDate}>{formatRelative(m.createdAt, now)}</span>
              <span className={s.memActions}>
                {m.sourceSessionId && <Button size="sm" variant="ghost" onClick={() => navigate({ name: "session", worldId, sessionId: m.sourceSessionId!, replay: true })}>View source</Button>}
                <Button size="sm" variant="ghost" onClick={() => void forget(m)}>Forget</Button>
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ── Knowledge (Could; mock with ribbon) ─────────────────────────────────────
export function KnowledgeTab({ c }: { c: Character }) {
  const q = useKnowledge(c.id);
  const [over, setOver] = useState(false);
  const docs = q.data ?? [];
  const kb = (n?: number) => (n ? (n > 1e6 ? `${(n / 1e6).toFixed(1)} MB` : `${Math.round(n / 1e3)} KB`) : "");
  const mock = () => toast({ variant: "info", text: "Knowledge uploads arrive with RAG in v1.1. This is a preview." });
  return (
    <div className={s.mem}>
      <div className={s.ribbon}>Preview: final design by AI team</div>
      <button
        type="button"
        className={cx(s.drop, over && s.dropOver)}
        onDragOver={(e) => { e.preventDefault(); setOver(true); }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); mock(); }}
        onClick={mock}
      >
        <span className={s.dropGlyph} aria-hidden="true">⇪</span>
        <span>{docs.length ? "Drop more documents" : `Drop documents to teach ${c.profile.name.split(" ")[0]}.`}</span>
        <span className={s.small}>PDF, TXT, MD, CSV · or click to upload</span>
      </button>
      {docs.length > 0 && (
        <ul className={s.docs}>
          {docs.map((d) => (
            <li key={d.id} className={s.doc}>
              <span className={s.docType}>{d.type.toUpperCase()}</span>
              <span className={s.docTitle}>{d.title}</span>
              <span className={s.small}>{kb(d.bytes)}</span>
              <Tape tone={d.status === "indexed" ? "ok" : d.status === "failed" ? "error" : "ink"} size="sm">{d.status}</Tape>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
