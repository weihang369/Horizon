// One log row (C): character bubble / Readable panel, user bubble, moderator & host lines, system notes,
// inline error tapes, stopped / interrupted states, reactions, regenerate variants ‹ 1/2 ›.
// Streaming text is the smoothed store value (useStreamText, R12); Markdown renders only once the turn ends.
import { memo, useMemo, useState, type CSSProperties } from "react";
import type { Character, Message } from "../../contract/types";
import { useStreamText } from "../../client/hooks";
import { client } from "../../client";
import { openOverlay, selectInsight, toast } from "../../app/layers";
import { run } from "../../app/errors";
import { emotionMeta } from "../../character/emotionMeta";
import { PaletteScope } from "../../theme/PaletteScope";
import { Tape } from "../../ui/Tape";
import { Tooltip } from "../../ui/Data";
import { cx } from "../../ui/cx";
import { InfoIcon, KeyIcon, RegenIcon } from "../../ui/icons";
import { plainText, renderMarkdown } from "./markdown";
import { firstName, READABLE_CHARS, useSessionCtx } from "./sessionContext";
import s from "./SessionLog.module.css";

export interface MessageRowProps {
  m: Message;
  chars: Record<string, Character>;
  variant: "chat" | "script";
  selected: boolean;
  /** Offer ↻ (last character message of a live 1:1 / group session). */
  canRegenerate: boolean;
  /** Row appeared after mount (animate in). */
  fresh: boolean;
  /** Show the full actions row (copy, insight). */
  onOpenInsight?: (id: string) => void;
}

function StreamingText({ id, fallback }: { id: string; fallback: string }) {
  const live = useStreamText(id);
  const text = live ?? fallback;
  if (!text) return <TypingDots />;
  return (
    <span className={s.streamText}>
      {text}
      <span className={s.caret} aria-hidden="true" />
    </span>
  );
}

export function TypingDots({ label }: { label?: string }) {
  return (
    <span className={s.dots} role="status" aria-label={label ?? "Typing"}>
      <i /><i /><i />
    </span>
  );
}

function authorLabel(m: Message, chars: Record<string, Character>): { name: string; char?: Character } {
  if (m.author.type === "character" && m.author.characterId) {
    const c = chars[m.author.characterId];
    return { name: c ? firstName(c.profile.name) : "…", char: c };
  }
  if (m.author.type === "host") return { name: "Host" };
  if (m.author.type === "user") return { name: m.kind === "chat" ? "You" : m.kind === "direction" ? "Director" : "Moderator" };
  return { name: "" };
}

const KIND_TAPE: Partial<Record<Message["kind"], string>> = {
  steer: "Moderator · Ask",
  interject: "Moderator",
  direction: "Director's note",
  narration: "Host",
  summary: "Summary",
  verdict: "Verdict",
};

function ErrorActions({ m, char }: { m: Message; char?: Character }) {
  const ctx = useSessionCtx();
  const live = ctx && !ctx.replay;
  if (!m.error || !live) return null;
  const sid = m.sessionId;
  const regen = () => void run(() => client.chat.regenerate(sid, m.id));
  if (m.error.code === "energy_exhausted") return null;
  const label = m.error.code === "content_refused" ? "Regenerate" : m.error.retryable ? "Retry" : null;
  return (
    <div className={s.errRow} role="alert">
      <Tape tone="error" size="sm">Warning</Tape>
      <span className={s.errMsg}>{m.error.message}<span className={s.errCode}> · {m.error.code}</span></span>
      {label && char && (
        <button type="button" className={s.textBtn} onClick={regen}>{label}</button>
      )}
    </div>
  );
}

function AsleepNote({ m, chars }: { m: Message; chars: Record<string, Character> }) {
  const ctx = useSessionCtx();
  const [waiting, setWaiting] = useState(false);
  const cid = m.targetCharacterId;
  const c = cid ? chars[cid] : undefined;
  const live = !!ctx && !ctx.replay;
  return (
    <PaletteScope paletteId={c?.paletteId} className={s.asleep}>
      <span className={s.zzz} aria-hidden="true">Zzz</span>
      <span className={s.asleepText}>{m.content}</span>
      {live && cid && !waiting && (
        <span className={s.asleepActions}>
          <button
            type="button"
            className={cx(s.chipBtn, s.chipPrimary)}
            onClick={() => (ctx?.demo ? openOverlay("O05", { reason: "Topping up energy needs your OpenRouter key." }) : openOverlay("O27", { characterId: cid, sessionId: m.sessionId }))}
          >
            {ctx?.demo && <KeyIcon width={12} height={12} />}⚡ Top up
          </button>
          <button type="button" className={s.chipBtn} onClick={() => { setWaiting(true); toast({ variant: "info", text: `${c ? firstName(c.profile.name) : "They"} will wake up as energy recharges.` }); }}>
            Wait
          </button>
        </span>
      )}
    </PaletteScope>
  );
}

function Reactions({ m, chars }: { m: Message; chars: Record<string, Character> }) {
  if (!m.reactions?.length) return null;
  // Latest reaction per character.
  const by = new Map<string, NonNullable<Message["reactions"]>[number]>();
  for (const r of m.reactions) by.set(r.characterId, r);
  return (
    <ul className={s.reactions} aria-label="Reactions">
      {[...by.values()].map((r) => {
        const c = chars[r.characterId];
        const name = c ? firstName(c.profile.name) : "";
        const meta = emotionMeta[r.emotion];
        return (
          <li key={r.characterId}>
            <PaletteScope paletteId={c?.paletteId} className={s.reaction} style={{ "--rx-d": `${(r.at.length % 5) * 20}ms` } as CSSProperties}>
              <span className={s.rxHead} aria-hidden="true">{name.slice(0, 1)}</span>
              <span className={s.rxIcon} aria-hidden="true">{meta.icon}</span>
              <span className="sr-only">{name} reacted {meta.label.toLowerCase()}</span>
            </PaletteScope>
          </li>
        );
      })}
    </ul>
  );
}

function MessageRowImpl({ m, chars, variant, selected, canRegenerate, fresh, onOpenInsight }: MessageRowProps) {
  const ctx = useSessionCtx();
  const { name, char } = authorLabel(m, chars);
  const streaming = m.status === "streaming";
  const [viewVariant, setViewVariant] = useState<string | null>(null);

  const variants = m.variants && m.variants.length > 1 ? m.variants : null;
  const activeIdx = variants ? Math.max(0, variants.findIndex((v) => v.id === m.activeVariantId)) : 0;
  const shownIdx = variants && viewVariant ? Math.max(0, variants.findIndex((v) => v.id === viewVariant)) : activeIdx;
  const content = variants && !streaming && shownIdx !== activeIdx ? variants[shownIdx].content : m.content;
  const body = useMemo(() => (streaming ? null : renderMarkdown(content)), [streaming, content]);

  // ── System notes ──
  if (m.kind === "system_note") {
    if (m.error?.code === "energy_exhausted" || /asleep/i.test(m.content)) {
      return <li className={cx(s.row, s.noteRow, fresh && s.fresh)} data-kind="asleep"><AsleepNote m={m} chars={chars} /></li>;
    }
    return (
      <li className={cx(s.row, s.noteRow, fresh && s.fresh)} data-kind="note">
        <span className={s.note}><span>{m.content}</span></span>
      </li>
    );
  }

  const isChar = m.author.type === "character";
  const isUser = m.author.type === "user" && m.kind === "chat";
  const tape = KIND_TAPE[m.kind];
  const readable = isChar && variant === "chat" && !streaming && (ctx?.readable || content.length > READABLE_CHARS);
  const emo = isChar && m.emotion ? emotionMeta[m.emotion] : null;
  const selectable = isChar && !!ctx?.insightOpen;

  const select = () => {
    if (selectable) selectInsight(m.id);
  };
  const copy = () => {
    void navigator.clipboard?.writeText(plainText(content)).then(
      () => toast({ variant: "success", text: "Copied to clipboard." }),
      () => toast({ variant: "warn", text: "Couldn't copy." }),
    );
  };
  const regen = () => {
    if (ctx?.demo) return void openOverlay("O05", { reason: "Regenerating a reply needs your OpenRouter key." });
    void run(() => client.chat.regenerate(m.sessionId, m.id));
  };

  const statusTag = m.status === "interrupted"
    ? m.interruptedBy === "user"
      ? <span className={s.stopped}>(stopped)</span>
      : <span className={s.interrupted}>(interrupted)</span>
    : null;
  const cutActions = m.status === "interrupted" && m.interruptedBy !== "user" && ctx && !ctx.replay && isChar;

  if (variant === "script") {
    return (
      <li className={cx(s.row, s.scriptRow, fresh && s.fresh, selected && s.selected)} data-kind={m.kind} onClick={select}>
        <PaletteScope paletteId={char?.paletteId} className={s.scriptWho}>
          <span className={cx(s.nameTape, !isChar && s.nameTapeInk)}>{tape && !isChar ? tape : name}</span>
        </PaletteScope>
        <span className={s.scriptText} aria-hidden={streaming || undefined}>
          {streaming ? <StreamingText id={m.id} fallback={m.content} /> : body}
          {statusTag}
        </span>
        <Reactions m={m} chars={chars} />
      </li>
    );
  }

  return (
    <li
      className={cx(s.row, isUser ? s.userRow : s.charRow, !isChar && !isUser && s.modRow, fresh && s.fresh, selected && s.selected, selectable && s.selectable)}
      data-kind={m.kind}
      data-status={m.status}
      data-mid={m.id}
      onClick={select}
    >
      <PaletteScope paletteId={char?.paletteId} className={s.msg}>
        <div className={s.who}>
          {isUser ? (
            <span className={s.youTag}>You</span>
          ) : isChar ? (
            <span className={s.nameTape}>{name}</span>
          ) : (
            <Tape tone={m.kind === "narration" ? "ink" : "paper"} size="sm">{tape ?? name}</Tape>
          )}
          {m.debate?.side && <Tape tone={m.debate.side} size="sm" className={s.sideTape}>{m.debate.side === "prop" ? "Prop" : "Opp"}</Tape>}
          {emo && (
            <span className={s.emo} title={`${emo.label}${m.emotionSource ? ` · ${m.emotionSource}` : ""}`}>
              <span aria-hidden="true">{emo.icon}</span>
              <span className={s.emoLabel}>{emo.label}</span>
            </span>
          )}
          {selected && <span className={s.insightTag}>Insight</span>}
        </div>
        <div
          className={cx(s.bubble, isUser && s.userBubble, readable && s.readable, !isChar && !isUser && s.modBubble, streaming && s.isStreaming)}
          aria-hidden={streaming || undefined}
        >
          {streaming ? <StreamingText id={m.id} fallback={m.content} /> : <div className={s.md}>{body}</div>}
          {statusTag}
        </div>
        {streaming && <span className="sr-only">{name} is typing</span>}
        {m.error && <ErrorActions m={m} char={char} />}
        {(isChar || isUser) && !streaming && (
          <div className={s.meta}>
            {isChar && <Reactions m={m} chars={chars} />}
            {variants && (
              <span className={s.variants} aria-label="Reply variants">
                <button type="button" aria-label="Previous variant" disabled={shownIdx === 0} onClick={(e) => { e.stopPropagation(); setViewVariant(variants[shownIdx - 1].id); }}>‹</button>
                <span className={s.variantCount}>{shownIdx + 1}/{variants.length}</span>
                <button type="button" aria-label="Next variant" disabled={shownIdx === variants.length - 1} onClick={(e) => { e.stopPropagation(); setViewVariant(variants[shownIdx + 1].id); }}>›</button>
                {shownIdx !== activeIdx && <span className={s.variantNote}>not in context</span>}
              </span>
            )}
            {cutActions && (
              <span className={s.cutActions}>
                <button type="button" className={cx(s.chipBtn, s.chipPrimary)} onClick={(e) => { e.stopPropagation(); regen(); }}>Continue</button>
                <button type="button" className={s.chipBtn} onClick={(e) => { e.stopPropagation(); regen(); }}>Regenerate</button>
              </span>
            )}
            <span className={s.actions}>
              <button type="button" className={s.act} onClick={(e) => { e.stopPropagation(); copy(); }} aria-label="Copy message">Copy</button>
              {isChar && onOpenInsight && (
                <Tooltip content="See how they thought (I)">
                  <button type="button" className={s.act} onClick={(e) => { e.stopPropagation(); onOpenInsight(m.id); }} aria-label="Open Insight for this message">
                    <InfoIcon width={14} height={14} />
                  </button>
                </Tooltip>
              )}
              {canRegenerate && (
                <button type="button" className={s.act} onClick={(e) => { e.stopPropagation(); regen(); }} aria-label="Regenerate reply">
                  {ctx?.demo ? <KeyIcon width={13} height={13} /> : <RegenIcon width={14} height={14} />}
                </button>
              )}
            </span>
          </div>
        )}
      </PaletteScope>
    </li>
  );
}

export const MessageRow = memo(MessageRowImpl);
