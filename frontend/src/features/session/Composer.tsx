// Composer: minimal working foundation version (Builder C replaces it; Builder D renders it). Owner: EE (stub).
// Enter = send, Shift+Enter = newline, Ctrl+Enter = send (APP-10 AC3). Typed text is kept on failure (STATE-03).
import { useState } from "react";
import { client } from "../../client";
import type { SessionRuntimeView } from "../../client/hooks";
import { run } from "../../app/errors";
import { Button } from "../../ui/Button";

export interface ComposerProps {
  rt?: SessionRuntimeView;
  sessionId: string;
  /** Override the send action (Step in, Ask…). Defaults to chat.send. */
  onSend?: (text: string) => Promise<unknown>;
  mentions?: string[];
  placeholder?: string;
  disabled?: boolean;
}

export function Composer({ rt, sessionId, onSend, mentions, placeholder = "Say something…", disabled }: ComposerProps) {
  const [text, setText] = useState("");
  const streaming = !!rt?.streamingId;
  const send = async () => {
    const t = text.trim();
    if (!t || disabled) return;
    const ok = await run(() => (onSend ? onSend(t) : client.chat.send(sessionId, t, { mentions })).then(() => true));
    if (ok) setText("");
  };
  return (
    <form
      onSubmit={(e) => { e.preventDefault(); void send(); }}
      style={{ display: "flex", gap: 12, padding: "12px 24px", alignItems: "flex-end" }}
    >
      <textarea
        aria-label="Message"
        value={text}
        rows={1}
        disabled={disabled}
        placeholder={placeholder}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (!e.shiftKey || e.ctrlKey)) {
            e.preventDefault();
            void send();
          }
        }}
        style={{ flex: 1, minHeight: 44, resize: "none", font: "inherit", padding: 10 }}
      />
      {streaming
        ? <Button type="button" variant="secondary" onClick={() => void run(() => client.chat.stop(sessionId))}>Stop</Button>
        : <Button type="submit" disabled={disabled || !text.trim()}>Send</Button>}
    </form>
  );
}
