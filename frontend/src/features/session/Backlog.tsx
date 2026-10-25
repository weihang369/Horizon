// O10 Backlog (CHAT-09): a full-screen visual-novel log (`L`) with in-session search and Markdown export.
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useStore } from "zustand";
import { client } from "../../client";
import type { OverlayComponentProps } from "../../app/overlayTypes";
import { run } from "../../app/errors";
import { toast } from "../../app/layers";
import { useShortcut } from "../../app/shortcuts";
import { emotionMeta } from "../../character/emotionMeta";
import type { Message } from "../../contract/types";
import { entities } from "../../stores/entities";
import { PaletteScope } from "../../theme/PaletteScope";
import { Button, IconButton } from "../../ui/Button";
import { CloseIcon, SearchIcon } from "../../ui/icons";
import { RansomText } from "../../ui/RansomText";
import { CitedText, SourcesStrip } from "./Citations";
import { plainText } from "./markdown";
import { firstName } from "./sessionContext";
import { useSlotRuntime } from "./slot";
import s from "./Backlog.module.css";

function highlight(text: string, q: string): ReactNode {
  if (!q) return text;
  const lower = text.toLowerCase();
  const needle = q.toLowerCase();
  const out: ReactNode[] = [];
  let at = 0;
  let i = lower.indexOf(needle);
  while (i >= 0) {
    if (i > at) out.push(text.slice(at, i));
    out.push(<mark key={i} className={s.hit}>{text.slice(i, i + q.length)}</mark>);
    at = i + q.length;
    i = lower.indexOf(needle, at);
  }
  out.push(text.slice(at));
  return out;
}

export function Backlog({ sessionId, close }: OverlayComponentProps<"O10">) {
  const { runtime } = useSlotRuntime(sessionId);
  const chars = useStore(entities, (st) => st.chars);
  const [q, setQ] = useState("");
  const root = useRef<HTMLDivElement>(null);
  const search = useRef<HTMLInputElement>(null);
  // Focus the panel, not the search: L must toggle the backlog closed (QA-02); "/" jumps to the search.
  useEffect(() => root.current?.focus({ preventScroll: true }), []);
  useShortcut("l", close);
  useShortcut("/", (e) => {
    e.preventDefault();
    search.current?.focus();
  });

  const lines = useMemo(() => {
    if (!runtime) return [] as { m: Message; text: string; who: string }[];
    return runtime.order.map((id) => runtime.messages[id]).filter(Boolean).map((m) => {
      const c = m.author.characterId ? chars[m.author.characterId] : undefined;
      const who = m.author.type === "character" ? firstName(c?.profile.name) : m.author.type === "user" ? (m.kind === "chat" ? "You" : m.kind === "direction" ? "Director" : "Moderator") : m.author.type === "host" ? "Host" : "";
      return { m, text: plainText(m.content), who };
    });
  }, [runtime, chars]);

  const query = q.trim();
  const shown = query ? lines.filter((l) => l.text.toLowerCase().includes(query.toLowerCase()) || l.who.toLowerCase().includes(query.toLowerCase())) : lines;

  const exportMd = async () => {
    const md = await run(() => client.sessions.export(sessionId));
    if (!md) return;
    const blob = new Blob([md], { type: "text/markdown" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${(runtime?.session.title ?? "session").replace(/[^\w-]+/g, "-").toLowerCase()}.md`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    toast({ variant: "success", text: "Transcript exported as Markdown." });
  };

  return (
    <div ref={root} tabIndex={-1} className={s.backlog} role="dialog" aria-modal="false" aria-label="Backlog">
      <header className={s.head}>
        <RansomText text="BACKLOG" size={44} as="h2" tone="mixed" />
        <span className={s.title}>{runtime?.session.title}</span>
        <label className={s.search}>
          <SearchIcon width={16} height={16} aria-hidden="true" />
          <input
            ref={search}
            type="search"
            value={q}
            placeholder="Search this conversation  ( / )"
            aria-label="Search this conversation"
            onChange={(e) => setQ(e.target.value)}
          />
          {query && <span className={s.count}>{shown.length} hit{shown.length === 1 ? "" : "s"}</span>}
        </label>
        <Button variant="secondary" size="sm" onClick={() => void exportMd()}>Export .md</Button>
        <IconButton label="Close backlog (L)" size="sm" onClick={close}><CloseIcon /></IconButton>
      </header>
      <ol className={s.lines}>
        {shown.map(({ m, text, who }) => {
          const c = m.author.characterId ? chars[m.author.characterId] : undefined;
          if (m.kind === "system_note") return <li key={m.id} className={s.note}>{highlight(text, query)}</li>;
          return (
            <li key={m.id} className={s.line} data-user={m.author.type === "user" || undefined}>
              <PaletteScope paletteId={c?.paletteId} className={s.who}>
                <span className={s.whoTape}>{who}</span>
                {m.emotion && <span className={s.emo} title={emotionMeta[m.emotion].label}>{emotionMeta[m.emotion].icon}</span>}
              </PaletteScope>
              <PaletteScope paletteId={c?.paletteId} className={s.body}>
                <p className={s.text}>
                  <CitedText text={text} cites={m.citations} paletteId={c?.paletteId} characterId={m.author.characterId} mark={(t) => highlight(t, query)} />
                  {m.status === "interrupted" && <em className={s.cut}> ({m.interruptedBy === "user" ? "stopped" : "interrupted"})</em>}
                </p>
                {m.citations?.length ? <SourcesStrip cites={m.citations} characterId={m.author.characterId} compact /> : null}
              </PaletteScope>
            </li>
          );
        })}
        {query && !shown.length && (
          <li className={s.empty}>
            <span>No lines match ‘{query}’.</span>
            <Button size="sm" variant="secondary" onClick={() => setQ("")}>Clear</Button>
          </li>
        )}
      </ol>
    </div>
  );
}
