// SessionLog (C): the one message log every session layout renders (S07 here; S09/S10/S12 via Builder D).
// Props are additive over the foundation version: { rt, variant?, className? } still work unchanged.
// Auto-scroll follows unless the user scrolled up (then a "↓ New message" pill, CHAT-02 AC2); role="log"
// announces completed messages only (streaming text is aria-hidden until turn.end).
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import type { SessionRuntimeView } from "../../client/hooks";
import { openOverlay, selectInsight } from "../../app/layers";
import { useUi } from "../../stores/ui";
import { PaletteScope } from "../../theme/PaletteScope";
import { cx } from "../../ui/cx";
import { MessageRow, TypingDots } from "./MessageRow";
import { firstName, isCharacterMsg, latestCharacterMessageId, useChars, useSessionCtx } from "./sessionContext";
import s from "./SessionLog.module.css";

export interface SessionLogProps {
  rt: SessionRuntimeView;
  /** Script style (Watch). */
  variant?: "chat" | "script";
  className?: string;
  /** Additive: hide the typing row (layouts that show thinking on stage). */
  hideThinking?: boolean;
  /** Additive: empty-state copy when there are no messages yet. */
  emptyText?: string;
}

const STICK_PX = 56;

export function SessionLog({ rt, variant = "chat", className, hideThinking, emptyText }: SessionLogProps) {
  const ctx = useSessionCtx();
  const chars = useChars();
  const scroller = useRef<HTMLDivElement>(null);
  const inner = useRef<HTMLOListElement>(null);
  const stick = useRef(true);
  const [unseen, setUnseen] = useState(0);
  const lastCount = useRef(rt.order.length);
  const initial = useRef<Set<string> | null>(null);
  if (initial.current === null && rt.order.length) initial.current = new Set(rt.order);
  const insightOpen = useUi((u) => u.layers.some((l) => l.id === "O08"));
  const insightSel = useUi((u) => u.insight.messageId);
  const list = rt.list;
  const sessionId = rt.session?.id;

  const selectedId = insightOpen ? insightSel ?? latestCharacterMessageId(list) : undefined;
  const mode = rt.session?.mode;
  const live = !!ctx && !ctx.replay && !ctx.isSeed && rt.session?.status !== "ended";

  // ↻ on the last character message (CHAT-06), 1:1 and group only.
  const regenId = useMemo(() => {
    if (!live || rt.streamingId || (mode !== "one_on_one" && mode !== "group")) return undefined;
    const last = list[list.length - 1];
    return isCharacterMsg(last) && last.status !== "streaming" && !last.error ? last.id : undefined;
  }, [live, rt.streamingId, mode, list]);

  // Only the newest "asleep" note per character keeps its Top up · Wait actions.
  const staleNotes = useMemo(() => {
    const seen = new Set<string>();
    const stale = new Set<string>();
    for (let i = list.length - 1; i >= 0; i--) {
      const m = list[i];
      if (m.kind !== "system_note" || !(m.error?.code === "energy_exhausted" || /asleep/i.test(m.content))) continue;
      const k = m.targetCharacterId ?? "";
      if (seen.has(k)) stale.add(m.id);
      else seen.add(k);
    }
    return stale;
  }, [list]);

  const toBottom = useCallback((smooth = false) => {
    const el = scroller.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: smooth ? "smooth" : "auto" });
  }, []);

  // Pin to the bottom while content grows (tokens re-render only the streaming row, so observe size).
  useLayoutEffect(() => {
    const el = inner.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => {
      if (stick.current) toBottom();
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [toBottom]);

  useLayoutEffect(() => {
    const added = rt.order.length - lastCount.current;
    lastCount.current = rt.order.length;
    if (added <= 0) return;
    if (stick.current) toBottom();
    else setUnseen((n) => n + added);
  }, [rt.order.length, toBottom]);

  // Selected row follows into view (Insight ↑↓).
  useEffect(() => {
    if (!selectedId) return;
    const row = scroller.current?.querySelector<HTMLElement>(`[data-mid="${CSS.escape(selectedId)}"]`);
    row?.scrollIntoView({ block: "nearest" });
  }, [selectedId]);

  const onScroll = () => {
    const el = scroller.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < STICK_PX;
    stick.current = atBottom;
    if (atBottom && unseen) setUnseen(0);
  };

  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (!insightOpen || (e.key !== "ArrowUp" && e.key !== "ArrowDown")) return;
    const ids = list.filter(isCharacterMsg).map((m) => m.id);
    if (!ids.length) return;
    e.preventDefault();
    const cur = selectedId ? ids.indexOf(selectedId) : ids.length - 1;
    const next = Math.max(0, Math.min(ids.length - 1, cur + (e.key === "ArrowUp" ? -1 : 1)));
    selectInsight(ids[next]);
  };

  const openInsight = useCallback((id: string) => {
    if (!sessionId) return;
    if (insightOpen) selectInsight(id);
    else openOverlay("O08", { sessionId, messageId: id });
  }, [sessionId, insightOpen]);

  const thinkingChar = rt.thinkingId && !rt.streamingId ? chars[rt.thinkingId] : undefined;

  return (
    <div className={cx(s.wrap, className)} data-variant={variant}>
      <div
        ref={scroller}
        className={s.scroller}
        onScroll={onScroll}
        onKeyDown={onKey}
        tabIndex={0}
        role="region"
        aria-label={insightOpen ? "Conversation log. Use arrow keys to pick a message for Insight." : "Conversation log"}
      >
        <ol ref={inner} role="log" aria-live="polite" aria-relevant="additions text" className={s.list}>
          {!list.length && !rt.thinkingId && (
            <li className={s.empty}>{emptyText ?? (rt.status === "loading" ? "" : "The stage is set. Say hello.")}</li>
          )}
          {list.map((m) => (
            <MessageRow
              key={m.id}
              m={m}
              chars={chars}
              variant={variant}
              selected={m.id === selectedId}
              canRegenerate={m.id === regenId}
              fresh={!!initial.current && !initial.current.has(m.id)}
              stale={staleNotes.has(m.id)}
              onOpenInsight={variant === "chat" ? openInsight : undefined}
            />
          ))}
          {thinkingChar && !hideThinking && (
            <li className={cx(s.row, variant === "script" ? s.scriptRow : s.charRow, s.fresh)} data-kind="thinking">
              <PaletteScope paletteId={thinkingChar.paletteId} className={s.msg}>
                <div className={s.who}><span className={s.nameTape}>{firstName(thinkingChar.profile.name)}</span></div>
                <div className={cx(s.bubble, s.thinkingBubble)}>
                  <TypingDots label={`${firstName(thinkingChar.profile.name)} is thinking`} />
                </div>
              </PaletteScope>
            </li>
          )}
        </ol>
      </div>
      {unseen > 0 && (
        <button
          type="button"
          className={s.newPill}
          onClick={() => {
            stick.current = true;
            setUnseen(0);
            toBottom(true);
          }}
        >
          ↓ New message{unseen > 1 ? `s · ${unseen}` : ""}
        </button>
      )}
    </div>
  );
}
