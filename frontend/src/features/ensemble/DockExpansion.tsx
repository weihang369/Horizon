// O12 DockExpansion (R5, UXA D3) — Builder D. Ask… / Interject / Director's note / Step in slide up 120 px from the
// dock over the log (240 ms slam), keep their draft per session + kind, and collapse on Esc (LayerStack step 2).
// Ask…/Interject hold the debate queue at the next boundary while open (NEXT chip shows HELD).
import { useEffect, useRef, useState } from "react";
import { client } from "../../client";
import type { DebateConfig } from "../../contract/types";
import type { OverlayComponentProps } from "../../app/overlayTypes";
import { reportError } from "../../app/errors";
import { PortraitCard } from "../../character";
import { PaletteScope } from "../../theme";
import { Button, CloseIcon, IconButton, SendIcon, Tape, TextArea } from "../../ui";
import { draftKey, firstName, getDraft, setDraft, useCharMap, useSlot } from "./shared";
import s from "./Dock.module.css";

const COPY = {
  ask: { tape: "Ask…", label: "Your question", placeholder: "Ask them something directly…", hint: "Only they answer. Moderator line, house style." },
  interject: { tape: "Interject", label: "Moderator note", placeholder: "A note every debater hears…", hint: "Seen by all debaters. Logged as MODERATOR." },
  direction: { tape: "🎬 Director's note", label: "Scene direction", placeholder: "The rain stops.", hint: "A scene event, shown as a stage direction. You're not in the scene." },
  stepin: { tape: "Step in", label: "Speak as yourself", placeholder: "Say something to them…", hint: "The scene pauses. Up to two of them answer, then resume when you're ready." },
} as const;

export function DockExpansion({ sessionId, kind, characterId, close }: OverlayComponentProps<"O12">) {
  const slot = useSlot(sessionId);
  const chars = useCharMap();
  const session = slot?.runtime?.session;
  const copy = COPY[kind];
  const key = draftKey(sessionId, kind);
  const [text, setText] = useState(() => getDraft(key));
  const [target, setTarget] = useState<string | undefined>(characterId ?? (kind === "ask" ? getDraft(`${key}:target`) || undefined : undefined));
  const [sending, setSending] = useState(false);
  const area = useRef<HTMLTextAreaElement>(null);

  useEffect(() => setDraft(key, text), [key, text]);
  useEffect(() => setDraft(`${key}:target`, target ?? ""), [key, target]);
  useEffect(() => {
    area.current?.focus({ preventScroll: true });
  }, [kind]);

  // Hold the debate queue at the next boundary while Ask…/Interject is open (auto-advance off, restored on close).
  const holds = session?.mode === "debate" && (kind === "ask" || kind === "interject");
  const autoWasOn = useRef(false);
  useEffect(() => {
    if (!holds) return;
    const cfg = session?.config as DebateConfig | null;
    if (!cfg?.autoAdvance) return;
    // Deferred a tick so StrictMode's double mount doesn't toggle the engine twice.
    const t = window.setTimeout(() => {
      autoWasOn.current = true;
      void client.debate.setAutoAdvance(sessionId, false).catch(() => (autoWasOn.current = false));
    }, 0);
    return () => {
      window.clearTimeout(t);
      if (autoWasOn.current) void client.debate.setAutoAdvance(sessionId, true).catch(() => {});
      autoWasOn.current = false;
    };
  }, [holds, sessionId]); // eslint-disable-line react-hooks/exhaustive-deps

  const cast = (session?.participants ?? []).map((p) => chars[p.characterId]).filter((c): c is NonNullable<typeof c> => !!c);
  const needsTarget = kind === "ask";
  const canSend = !!text.trim() && (!needsTarget || !!target) && !sending;

  const send = async () => {
    const t = text.trim();
    if (!canSend) return;
    setSending(true);
    let ok = true;
    try {
      if (kind === "ask") await client.debate.askCharacter(sessionId, target!, t);
      else if (kind === "interject") await client.debate.interject(sessionId, t);
      else if (kind === "direction") await client.watch.direct(sessionId, t);
      else await client.watch.stepIn(sessionId, t);
    } catch (err) {
      ok = false; // typed text is kept (STATE-03)
      reportError(err);
    }
    setSending(false);
    if (ok) {
      setText("");
      setDraft(key, "");
      close();
    }
  };

  return (
    <div className={s.expHost}>
      <div className={s.exp} role="dialog" aria-label={copy.tape} data-overlay="O12" data-kind={kind}>
        <div className={s.expHead}>
          <Tape tone="brand" size="sm">{copy.tape}</Tape>
          <span className={s.expHint}>{copy.hint}</span>
          <IconButton label="Collapse (Esc), draft kept" size="sm" className={s.expClose} onClick={close}>
            <CloseIcon />
          </IconButton>
        </div>
        {needsTarget && (
          <div className={s.targets} role="radiogroup" aria-label="Ask who">
            {cast.map((c) => {
              const p = session?.participants.find((x) => x.characterId === c.id);
              return (
                <PaletteScope key={c.id} paletteId={c.paletteId} as="span" style={{ display: "contents" }}>
                  <button
                    type="button"
                    role="radio"
                    aria-checked={target === c.id}
                    className={s.target}
                    onClick={() => {
                      setTarget(c.id);
                      area.current?.focus();
                    }}
                  >
                    <PortraitCard character={c} emotion={p?.currentEmotion ?? "neutral"} size="head" width={30} />
                    {firstName(c)}
                    {p?.side && <span style={{ opacity: 0.7, fontSize: 12 }}>{p.side.toUpperCase()}</span>}
                  </button>
                </PaletteScope>
              );
            })}
          </div>
        )}
        <form
          className={s.row}
          onSubmit={(e) => {
            e.preventDefault();
            void send();
          }}
        >
          <div className={s.field}>
          <TextArea
            ref={area}
            label={needsTarget && target ? `${copy.label} for ${firstName(chars[target])}` : copy.label}
            hideLabel
            rows={2}
            maxLength={kind === "direction" ? 300 : 1000}
            value={text}
            placeholder={needsTarget && !target ? "Pick who you're asking first…" : copy.placeholder}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (!e.shiftKey || e.ctrlKey)) {
                e.preventDefault();
                void send();
              }
            }}
          />
          </div>
          <Button type="submit" disabled={!canSend} iconRight={<SendIcon />}>
            {kind === "stepin" ? "Say it" : kind === "direction" ? "Direct" : "Send"}
          </Button>
        </form>
      </div>
    </div>
  );
}
