// S06 tab panels: Profile · Gallery · Theme · Sessions · Memory · Knowledge (PRF-01..08). Owner: Builder B.
import { useRef, useState } from "react";
import type { CSSProperties } from "react";
import { openOverlay, toast } from "@/app/layers";
import { reportError } from "@/app/errors";
import { client } from "@/client";
import { useJob, useKnowledge, useMemory, useNow, useSessions, useSettings } from "@/client/hooks";
import type { Character, Emotion, KnowledgeSource, MemoryItem, Session, ThemeSong } from "@/contract/types";
import { EMOTIONS } from "@/contract/types";
import { emotionMeta } from "@/character";
import { formatRelative } from "@/domain/format";
import { navigate } from "@/router";
import { Button, EmptyState, HalftoneDevelop, Skeleton, Tape } from "@/ui";
import { cx } from "@/ui/cx";
import { isRunning, startGeneration, useCharacterJobs, useEstimate } from "@/features/wizard/generate";
import { useAssetCompareWatcher } from "./compare";
import { ThemeTrack } from "./ThemeTrack";
import { ACCEPT, sortSources } from "./knowledge";
import { KnowledgeCard } from "./KnowledgeCard";
import { useKnowledgeProgress } from "./useKnowledgeProgress";
import s from "./profile.module.css";
import k from "./knowledge.module.css";

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
  return <ThemeTrack c={c} song={song} />;
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

// ── Knowledge (PRF-08, M5 design D20; the final presentation is AI-stage, so the ribbon stays) ─

export function KnowledgeTab({ c }: { c: Character }) {
  const q = useKnowledge(c.id);
  const keySet = useSettings().data?.openRouterKeyStatus === "set";
  const progress = useKnowledgeProgress();
  const pick = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const first = c.profile.name.split(" ")[0];
  const docs = sortSources(q.data ?? []);
  const cites = docs.reduce((n, d) => n + (d.citedCount ?? 0), 0);
  // One at a time, so the 20-source and duplicate checks see the previous file; each refusal is reported on its own.
  const add = async (files: File[]) => {
    for (const file of files) {
      try {
        await client.characters.addKnowledge(c.id, { file });
      } catch (err) {
        reportError(err);
      }
    }
  };
  const reindex = (d: KnowledgeSource) => void client.characters.reindexKnowledge(d.id).catch(reportError);
  const remove = (d: KnowledgeSource) => openOverlay("O03", {
    title: `Delete ${d.title}?`,
    body: "Its passages go; old citations keep their quotes.",
    confirmLabel: "Delete",
    onConfirm: () => client.characters.deleteKnowledge(d.id),
  });
  const drop = (
    <button
      type="button"
      className={cx(k.drop, docs.length > 0 && k.dropSlim, over && k.dropOver)}
      onDragOver={(e) => { e.preventDefault(); setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); void add([...e.dataTransfer.files]); }}
      onClick={() => pick.current?.click()}
    >
      <span className={k.dropGlyph} aria-hidden="true">⇪</span>
      <span className={k.dropText}>
        <b>{docs.length ? `Drop more documents to teach ${first}` : `Drop documents to teach ${first}.`}</b>
        <span>PDF, DOCX, MD or TXT · click to pick a file · or paste text</span>
      </span>
    </button>
  );
  return (
    <div className={k.wrap}>
      <input
        ref={pick}
        type="file"
        accept={ACCEPT}
        multiple
        hidden
        onChange={(e) => { const files = [...(e.target.files ?? [])]; e.target.value = ""; void add(files); }}
      />
      <div className={k.top}>
        <div className={s.ribbon}>Preview: final design by AI team</div>
        {docs.length > 0 && <p className={k.sum}>{docs.length} {docs.length === 1 ? "source" : "sources"}{cites ? <> · cited <b>{cites}×</b> in conversations</> : null}</p>}
        <Button size="sm" variant="secondary" className={k.paste} onClick={() => openOverlay("O29", { characterId: c.id, name: first })}>Paste text</Button>
      </div>
      {q.loading ? <Skeleton lines={3} height={64} /> : docs.length === 0 ? (
        <>
          {drop}
          <p className={s.small}>{first} answers from what you teach here and cites the passage with a [n] marker.</p>
        </>
      ) : (
        <>
          <ul className={k.grid}>
            {docs.map((d, i) => (
              <KnowledgeCard
                key={d.id}
                d={d}
                i={i}
                keySet={keySet}
                progress={d.status === "indexing" ? progress[d.id] : undefined}
                onOpen={() => openOverlay("O28", { sourceId: d.id, characterId: c.id })}
                onDelete={() => remove(d)}
                onReindex={() => reindex(d)}
              />
            ))}
          </ul>
          {drop}
        </>
      )}
    </div>
  );
}
