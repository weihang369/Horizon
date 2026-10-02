// SessionLog: minimal working foundation version (Builder C replaces it; Builder D renders it). Owner: EE (stub).
// Renders messages in order; the streaming message reads the smoothed text (useStreamText, R12).
import { useEffect, useRef } from "react";
import { useStore } from "zustand";
import type { Message } from "../../contract/types";
import { useStreamText } from "../../client/hooks";
import type { SessionRuntimeView } from "../../client/hooks";
import { entities } from "../../stores/entities";

export interface SessionLogProps {
  rt: SessionRuntimeView;
  /** Script style (Watch). */
  variant?: "chat" | "script";
  className?: string;
}

function Line({ m }: { m: Message }) {
  const live = useStreamText(m.status === "streaming" ? m.id : null);
  const name = useStore(entities, (s) => (m.author.characterId ? s.chars[m.author.characterId]?.profile.name : undefined));
  const who = m.author.type === "user" ? (m.kind === "chat" ? "You" : "MODERATOR") : m.author.type === "host" ? "HOST" : m.author.type === "system" ? "" : name ?? m.author.characterId;
  const text = m.status === "streaming" ? live ?? m.content : m.content;
  return (
    <li data-kind={m.kind} data-status={m.status} style={{ margin: "0 0 10px", opacity: m.kind === "system_note" ? 0.7 : 1 }}>
      {who && <strong>{who}{m.emotion ? ` [${m.emotion}]` : ""} ▸ </strong>}
      <span>{text}</span>
      {m.status === "streaming" && <span aria-hidden="true"> ▌</span>}
      {m.error && <em role="alert"> · {m.error.message}</em>}
    </li>
  );
}

export function SessionLog({ rt, variant = "chat", className }: SessionLogProps) {
  const end = useRef<HTMLLIElement>(null);
  const count = rt.order.length;
  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [count]);
  return (
    <ol role="log" aria-live="polite" data-variant={variant} className={className} style={{ listStyle: "none", margin: 0, padding: "16px 24px", overflowY: "auto", height: "100%" }}>
      {rt.list.map((m) => <Line key={m.id} m={m} />)}
      {rt.thinkingId && <li aria-label="typing">…</li>}
      <li ref={end} aria-hidden="true" />
    </ol>
  );
}
