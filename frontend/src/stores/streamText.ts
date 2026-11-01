// Streamed text, outside the session runtime (R12): one store write per frame, revealed by the StreamSmoother on
// the global ticker, so only <StreamingMessage id> re-renders while tokens arrive.
import { createStore } from "zustand/vanilla";
import { StreamSmoother } from "../engine/StreamSmoother";
import { onTick } from "../vfx/ticker";

export interface StreamTextState { text: Record<string, string> }

export const streamText = createStore<StreamTextState>(() => ({ text: {} }));

const smoother = new StreamSmoother();
let stopTick: (() => void) | null = null;

function ensureTicking(): void {
  if (stopTick) return;
  stopTick = onTick((dt) => {
    const { changed } = smoother.step(dt);
    if (changed.length) {
      streamText.setState((s) => {
        const text = { ...s.text };
        for (const [id, t] of changed) text[id] = t;
        return { text };
      });
    }
    if (smoother.size === 0 && stopTick) {
      stopTick();
      stopTick = null;
    }
  });
}

/** The full received text for a message (call once per coalesced batch, not per token). */
export function setStreamTarget(messageId: string, full: string, done = false): void {
  smoother.setTarget(messageId, full, done);
  // A new take (Regenerate's turn.start, content "") replaces what was shown: the old reply's text stayed on screen,
  // with the caret, until the first new token (pass 2 J2-04). The smoother restarted it; the store follows now.
  const shown = streamText.getState().text[messageId];
  if (shown !== undefined && !full.startsWith(shown)) {
    const v = smoother.visible(messageId) ?? full;
    streamText.setState((s) => ({ text: { ...s.text, [messageId]: v } }));
  }
  if (typeof requestAnimationFrame === "undefined") {
    smoother.flush(messageId);
    streamText.setState((s) => ({ text: { ...s.text, [messageId]: full } }));
    return;
  }
  ensureTicking();
}

/** Reveal immediately (seek, replay jump, reduced motion). */
export function flushStream(messageId?: string): void {
  const ids = messageId ? [messageId] : Object.keys(streamText.getState().text);
  const out: Record<string, string> = {};
  for (const id of ids) {
    smoother.flush(id);
    const v = smoother.visible(id);
    if (v !== undefined) out[id] = v;
  }
  if (Object.keys(out).length) streamText.setState((s) => ({ text: { ...s.text, ...out } }));
}

export function clearStream(messageIds?: string[]): void {
  if (!messageIds) {
    smoother.clear();
    streamText.setState({ text: {} });
    return;
  }
  // Mark each one revealed and finished, so the next tick drops it from the smoother without writing it back; an
  // unfinished entry left there (a session closed mid-reply) kept the ticker running every frame for good.
  for (const id of messageIds) {
    smoother.flush(id);
    const v = smoother.visible(id);
    if (v !== undefined) smoother.setTarget(id, v, true);
  }
  streamText.setState((s) => {
    const text = { ...s.text };
    for (const id of messageIds) delete text[id];
    return { text };
  });
}
