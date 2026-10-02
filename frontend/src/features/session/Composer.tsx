// Composer (C; Builder D renders it in DockExpansions). Props are a superset of the foundation version.
// <textarea> + mirrored highlight layer (mention chips), grows 1→6 lines, counter from 3,500, cap 4,000 (CHAT-02 AC5).
// Enter = send, Shift+Enter = newline, Ctrl+Enter = send (APP-10 AC3). The draft persists per session (store,
// survives errors/navigation/Esc). Send is a −12° parallelogram that morphs into a Stop square while streaming.
// Demo mode (R15): Send looks enabled with a key glyph and opens O05; the typed text is kept.
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type ClipboardEvent, type KeyboardEvent, type ReactNode } from "react";
import { useStore } from "zustand";
import { client } from "../../client";
import type { SessionRuntimeView } from "../../client/hooks";
import { useSettings } from "../../client/hooks";
import { closeOverlay, isOverlayOpen, openOverlay, toast } from "../../app/layers";
import { run } from "../../app/errors";
import { audio } from "../../audio/engine";
import { PaletteScope } from "../../theme/PaletteScope";
import { cx } from "../../ui/cx";
import { KeyIcon, SendIcon, StopIcon } from "../../ui/icons";
import { entities } from "../../stores/entities";
import { useUi } from "../../stores/ui";
import {
  backspaceMention, filterCandidates, insertMention, mentionBus, mentionIds, mentionQueryAt, mentionSpans, moveMention,
  type MentionCandidate,
} from "./mentions";
import { firstName, useSessionCtx } from "./sessionContext";
import s from "./Composer.module.css";

export interface ComposerProps {
  rt?: SessionRuntimeView;
  sessionId: string;
  /** Override the send action (Step in, Ask…). Defaults to chat.send. */
  onSend?: (text: string) => Promise<unknown>;
  mentions?: string[];
  placeholder?: string;
  disabled?: boolean;
  /** Additive: draft slot (defaults to the session, or `<session>:x` with a custom onSend). */
  draftKey?: string;
  /** Additive: focus the field on mount (default true). */
  autoFocus?: boolean;
  /** Additive: label for the send button (e.g. "Ask", "Interject"). */
  sendLabel?: string;
  /** Additive: extra controls before the field (e.g. D's responders menu). */
  leading?: ReactNode;
  /** Additive: compact = 1:1 inline composer inside the log column. */
  variant?: "dock" | "inline";
  /** Additive: registry DockProps pass-through (ignored). */
  worldId?: string;
  replay?: boolean;
}

export const MAX_CHARS = 4000;
const COUNTER_FROM = 3500;

// Drafts outlive the component (STATE-03, UXA §2.3).
const drafts = new Map<string, string>();
export const getDraft = (key: string): string => drafts.get(key) ?? "";

export function Composer({
  rt, sessionId, onSend, mentions, placeholder, disabled, draftKey, autoFocus = true, sendLabel, leading, variant = "dock",
}: ComposerProps) {
  const ctx = useSessionCtx();
  const settings = useSettings().data;
  const demo = ctx?.demo ?? settings?.demoMode ?? false;
  const key = draftKey ?? (onSend ? `${sessionId}:x` : sessionId);
  const [text, setTextState] = useState(() => getDraft(key));
  const ta = useRef<HTMLTextAreaElement>(null);
  const mirror = useRef<HTMLDivElement>(null);
  const pendingCaret = useRef<number | null>(null);
  const picker = useRef<{ start: number; caret: number } | null>(null);
  const [sending, setSending] = useState(false);
  const chars = useStore(entities, (st) => st.chars);

  const session = rt?.session;
  const streaming = !!rt?.streamingId && !onSend;
  const busy = streaming || (!!rt?.thinkingId && !onSend);

  const candidates = useMemo<MentionCandidate[]>(() => {
    const parts = session?.participants ?? [];
    if (parts.length < 2) return [];
    return parts.map((p) => ({ id: p.characterId, name: firstName(chars[p.characterId]?.profile.name) || p.characterId })).filter((c) => c.name);
  }, [session?.participants, chars]);

  const setText = (t: string, caret?: number) => {
    drafts.set(key, t);
    setTextState(t);
    if (caret !== undefined) pendingCaret.current = caret;
  };

  useEffect(() => {
    if (autoFocus && !disabled) ta.current?.focus({ preventScroll: true });
  }, [autoFocus, disabled]);

  // Grow 1→6 lines (max 160 px) from the mirror's height.
  useLayoutEffect(() => {
    const t = ta.current;
    const m = mirror.current;
    if (!t || !m) return;
    const h = Math.min(160, Math.max(m.scrollHeight, 0));
    t.style.height = `${h}px`;
    if (pendingCaret.current !== null) {
      t.setSelectionRange(pendingCaret.current, pendingCaret.current);
      pendingCaret.current = null;
    }
  }, [text]);

  useEffect(() => () => {
    if (picker.current) closeOverlay("O11");
  }, []);

  // Esc / outside click closed the picker on the LayerStack: forget the query.
  const pickerOpen = useUi((u) => u.layers.some((l) => l.id === "O11"));
  useEffect(() => {
    if (!pickerOpen && picker.current) {
      picker.current = null;
      mentionBus.setState({ items: [], active: 0 });
    }
  }, [pickerOpen]);

  const closePicker = () => {
    if (!picker.current) return;
    picker.current = null;
    mentionBus.setState({ items: [], active: 0 });
    if (isOverlayOpen("O11")) closeOverlay("O11");
  };

  const pick = (id: string) => {
    const p = picker.current;
    const c = candidates.find((x) => x.id === id);
    if (!p || !c) return closePicker();
    const r = insertMention(text, p.start, p.caret, c.name);
    closePicker();
    setText(r.text, r.caret);
    queueMicrotask(() => ta.current?.focus());
  };

  const syncPicker = (t: string, caret: number) => {
    if (!candidates.length) return;
    const q = mentionQueryAt(t, caret);
    if (!q) return closePicker();
    const items = filterCandidates(candidates, q.query);
    if (!items.length) return closePicker();
    picker.current = { start: q.start, caret };
    mentionBus.setState((st) => ({ items, active: Math.min(st.active, items.length - 1) }));
    const r = ta.current?.getBoundingClientRect();
    openOverlay("O11", {
      sessionId,
      query: q.query,
      anchor: r ? { x: r.x + 8, y: r.y, width: 0, height: 0 } : undefined,
      onPick: (id: string) => pickRef.current(id),
    });
  };
  const pickRef = useRef(pick);
  pickRef.current = pick;

  const send = async () => {
    const t = text.trim();
    if (!t || disabled || sending) return;
    if (demo && !onSend) {
      openOverlay("O05", { reason: "Live replies need your OpenRouter key. Your message is kept." });
      return;
    }
    if (busy) return;
    closePicker();
    setSending(true);
    const ids = mentions ?? mentionIds(t, candidates);
    const ok = await run(() => (onSend ? onSend(t) : client.chat.send(sessionId, t, ids.length ? { mentions: ids } : undefined)).then(() => true));
    setSending(false);
    if (ok) {
      audio.playSfx("ui_send");
      setText("");
    }
  };

  const stop = () => void run(() => client.chat.stop(sessionId));

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (picker.current && mentionBus.getState().items.length) {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        moveMention(e.key === "ArrowDown" ? 1 : -1);
        return;
      }
      if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        const st = mentionBus.getState();
        pick(st.items[st.active]?.id ?? "");
        return;
      }
    }
    if (e.key === "Backspace" && candidates.length) {
      const el = e.currentTarget;
      if (el.selectionStart === el.selectionEnd) {
        const r = backspaceMention(text, el.selectionStart, candidates);
        if (r) {
          e.preventDefault();
          setText(r.text, r.caret);
          return;
        }
      }
    }
    if (e.key === "Enter" && (!e.shiftKey || e.ctrlKey) && !e.nativeEvent.isComposing) {
      e.preventDefault();
      void send();
    }
  };

  const onPaste = (e: ClipboardEvent<HTMLTextAreaElement>) => {
    const pasted = e.clipboardData.getData("text");
    const el = e.currentTarget;
    const next = text.slice(0, el.selectionStart) + pasted + text.slice(el.selectionEnd);
    if (next.length <= MAX_CHARS) return;
    e.preventDefault();
    const room = MAX_CHARS - (text.length - (el.selectionEnd - el.selectionStart));
    const cut = text.slice(0, el.selectionStart) + pasted.slice(0, Math.max(0, room)) + text.slice(el.selectionEnd);
    setText(cut, el.selectionStart + Math.max(0, room));
    toast({ variant: "warn", text: `Messages are capped at ${MAX_CHARS.toLocaleString("en")} characters. The paste was trimmed.` });
  };

  const spans = useMemo(() => mentionSpans(text, candidates), [text, candidates]);
  const mirrorNodes = useMemo(() => {
    if (!spans.length) return text;
    const out: ReactNode[] = [];
    let at = 0;
    spans.forEach((sp, i) => {
      if (sp.start > at) out.push(text.slice(at, sp.start));
      out.push(
        <PaletteScope key={i} as="mark" paletteId={chars[sp.id]?.paletteId} className={s.chip}>{text.slice(sp.start, sp.end)}</PaletteScope>,
      );
      at = sp.end;
    });
    out.push(text.slice(at));
    return out;
  }, [text, spans, chars]);

  const firstChar = session?.participants[0] ? chars[session.participants[0].characterId] : undefined;
  const ph = placeholder ?? (session?.mode === "one_on_one" && firstChar ? `Talk to ${firstName(firstChar.profile.name)}…` : candidates.length ? "Say something… (@ to mention)" : "Say something…");
  const count = text.length;
  const label = sendLabel ?? "Send";
  const showStop = streaming;

  return (
    <form
      className={cx(s.composer, s[variant], showStop && s.isStreaming)}
      onSubmit={(e) => { e.preventDefault(); void send(); }}
      data-composer=""
    >
      <div className={s.row}>
        {leading}
        <div className={cx(s.field, disabled && s.fieldDisabled)}>
          <div ref={mirror} className={s.mirror} aria-hidden="true">
            {mirrorNodes}
            {"​"}
          </div>
          <textarea
            ref={ta}
            aria-label={ph.replace(/….*$/, "")}
            className={s.input}
            value={text}
            rows={1}
            maxLength={MAX_CHARS}
            disabled={disabled}
            placeholder={ph}
            spellCheck
            onChange={(e) => {
              setText(e.target.value);
              syncPicker(e.target.value, e.target.selectionStart);
            }}
            onSelect={(e) => {
              if (picker.current) syncPicker(e.currentTarget.value, e.currentTarget.selectionStart);
            }}
            onBlur={() => setTimeout(() => {
              if (document.activeElement !== ta.current) closePicker();
            }, 120)}
            onKeyDown={onKeyDown}
            onPaste={onPaste}
          />
          {count >= COUNTER_FROM && (
            <span className={cx(s.counter, count >= MAX_CHARS && s.counterMax)} aria-live="polite">
              {count.toLocaleString("en")} / {MAX_CHARS.toLocaleString("en")}
            </span>
          )}
        </div>
        {showStop ? (
          <button type="button" className={cx(s.send, s.stop)} onClick={stop} aria-label="Stop the reply (Ctrl+.)" title="Stop (Ctrl+.)">
            <span className={s.sendShape} aria-hidden="true" />
            <span className={s.sendContent}><StopIcon width={18} height={18} /></span>
          </button>
        ) : (
          <button
            type="submit"
            className={s.send}
            disabled={disabled || sending || (!demo && (!text.trim() || busy))}
            data-key-locked={demo && !onSend ? "" : undefined}
            aria-label={demo && !onSend ? `${label} (needs API key)` : label}
          >
            <span className={s.sendShape} aria-hidden="true" />
            <span className={s.sendContent}>
              {demo && !onSend && <KeyIcon width={14} height={14} />}
              {label}
              {!(demo && !onSend) && <SendIcon width={16} height={16} />}
            </span>
          </button>
        )}
      </div>
    </form>
  );
}
