// Screenplay → SessionEvents → (reducer) → messages + final session. Messages are produced BY the reducer,
// so replay equivalence holds by construction and the test proves the committed files still agree.
import type {
  DebateState, Message, Session, SessionEvent, StreamEvent, WatchConfig, WatchState,
} from "../../src/contract/types";
import { estimateTokens } from "../../src/domain/cost";
import { energyState } from "../../src/domain/energy";
import { initialRuntime, orderedMessages, reduceAll } from "../../src/engine/sessionReducer";
import { PRICING } from "../../src/mock/pricing.config";
import { createRng, iso } from "../../src/mock/rng";
import { citeKnowledge } from "../../src/mock/script/citations";
import { buildLineScript } from "../../src/mock/script/turnScript";
import type { ReactionSpec } from "../../src/mock/script/turnScript";
import { DEFAULT_TIMING } from "../../src/mock/timing.config";
import { CHUNK_BY_ID } from "./data/knowledge";
import type { Screenplay } from "./types";

const chunkRef = (id: string) => {
  const ref = CHUNK_BY_ID[id];
  if (!ref) throw new Error(`[seed-build] unknown knowledge chunk ${id}`);
  return ref;
};

export interface CompiledSession {
  session: Session;
  messages: Message[];
  events: SessionEvent[];
  /** ⚡ spent per character over the whole session. */
  spent: Record<string, number>;
}

const pad = (n: number, w: number) => String(n).padStart(w, "0");
const PHASE_LABEL = { opening: "OPENING", rebuttal: "REBUTTAL", closing: "CLOSING", verdict: "VERDICT", setup: "SETUP", ended: "ENDED" } as const;

interface RunResult {
  timeline: { t: number; evt: StreamEvent }[];
  spent: Record<string, number>;
  /** Per character: ⚡ spent up to and including the anchor beat, and the anchored remaining value. */
  anchors: Record<string, { spentThrough: number; remaining: number }>;
  anchorRelT: number | null;
  anchorAt: string | null;
}

function run(sp: Screenplay, startEnergy: Record<string, number>): RunResult {
  const rng = createRng(`screenplay:${sp.msgKey}`);
  const timing = DEFAULT_TIMING;
  const timeline: { t: number; evt: StreamEvent }[] = [];
  const push = (t: number, evt: StreamEvent) => timeline.push({ t: Math.round(t), evt });
  const sid = sp.session.id;
  const participants = sp.session.participants;
  const cast = participants.map((p) => p.characterId);
  const period = sp.period ?? "off_peak";
  const spent: Record<string, number> = Object.fromEntries(cast.map((c) => [c, 0]));
  const energy: Record<string, number> = { ...startEnergy };
  const anchors: RunResult["anchors"] = {};
  let anchorRelT: number | null = null;
  let anchorAt: string | null = null;

  let msgSeq = 0;
  let historyTokens = 0;
  const nextMsgId = () => `msg_${sp.msgKey}${pad(++msgSeq, 2)}`;
  const isDebate = sp.session.mode === "debate";
  const isWatch = sp.session.mode === "watch";
  let debate: DebateState | null = isDebate ? { ...(sp.session.initialState as DebateState) } : null;
  let watch: WatchState | null = isWatch ? { ...(sp.session.initialState as WatchState) } : null;
  const paceMs = isWatch ? (sp.session.config as WatchConfig).paceMs : 0;

  // Initial snapshot so Replay starts from the right place (participants neutral, state at its start).
  push(0, { type: "session.state", payload: { status: "active", state: sp.session.initialState ?? undefined, participants } });
  cast.forEach((c, i) => {
    push(5 + i, { type: "energy", payload: { characterId: c, current: energy[c], max: 1000, state: energyState(energy[c], 1000) } });
  });
  if (watch) push(20, { type: "watch.state", payload: { status: "playing", paceMs, turnsTaken: 0, turnLimit: watch.turnLimit } });

  let t = 400;
  const systemMessage = (content: string, kind: Message["kind"] = "system_note", author: Message["author"] = { type: "system" }): Message => ({
    id: nextMsgId(), sessionId: sid, seq: msgSeq, author, kind, content, status: "complete", createdAt: "",
  });
  const pushMessage = (at: number, m: Message, startMs: number | null) => {
    // createdAt is filled when absolute times are known (see finalize); keep relative here.
    push(at, { type: "message", payload: { message: { ...m, createdAt: startMs === null ? "" : iso(startMs + Math.round(at)) } } });
    historyTokens += estimateTokens(m.content);
  };

  for (const beat of sp.beats) {
    switch (beat.k) {
      case "wait":
        t += beat.ms;
        break;
      case "user": {
        t += beat.gapMs ?? 1600;
        const m: Message = {
          id: nextMsgId(), sessionId: sid, seq: msgSeq, author: { type: "user" }, kind: beat.kind ?? "chat",
          ...(beat.target ? { targetCharacterId: beat.target } : {}),
          content: beat.text, status: "complete", createdAt: "",
          ...(debate && beat.kind !== "direction" ? { debate: { phase: debate.phase, round: debate.round, iteration: debate.iteration } } : {}),
        };
        pushMessage(t, m, null);
        t += 250;
        break;
      }
      case "face":
        t += 500;
        push(t, { type: "emotion", payload: { characterId: beat.who, emotion: beat.emotion, source: "user" } });
        t += 300;
        break;
      case "phase": {
        t += 300;
        const iteration = beat.iteration ?? 1;
        push(t, { type: "phase", payload: { phase: beat.phase, round: beat.round, iteration } });
        if (debate) debate = { ...debate, phase: beat.phase, round: beat.round, iteration };
        pushMessage(t + 10, systemMessage(beat.label ?? `ROUND ${beat.round} · ${PHASE_LABEL[beat.phase]}`), null);
        t += 1400; // banner slam
        break;
      }
      case "host":
        t += 400;
        pushMessage(t, systemMessage(beat.text, "narration", { type: "host" }), null);
        t += 1800;
        break;
      case "system":
        t += 300;
        pushMessage(t, systemMessage(beat.text), null);
        t += 600;
        break;
      case "verdict": {
        t += 500;
        const round = debate?.round ?? 0;
        push(t, { type: "phase", payload: { phase: "verdict", round: round + 1, iteration: 1 } });
        if (debate) debate = { ...debate, phase: "verdict", round: round + 1, iteration: 1 };
        t += 1800;
        pushMessage(t, systemMessage(beat.text, "verdict"), null);
        if (debate) {
          debate = { ...debate, verdict: beat.verdict };
          push(t + 20, { type: "session.state", payload: { state: { ...debate } } });
        }
        t += 1200;
        break;
      }
      case "end": {
        t += 300;
        if (beat.status === "ended") {
          if (debate) {
            debate = { ...debate, phase: "ended", nextSpeakerId: undefined };
            push(t, { type: "phase", payload: { phase: "ended", round: debate.round, iteration: debate.iteration } });
          }
          push(t + 10, { type: "session.state", payload: { status: "ended", ...(debate ? { state: { ...debate } } : {}) } });
        } else {
          if (watch) {
            watch = { ...watch, status: beat.reason === "turn_cap" ? "ended" : "paused", nextSpeakerId: undefined };
            push(t, { type: "watch.state", payload: { status: watch.status, paceMs, turnsTaken: watch.turnsTaken, turnLimit: watch.turnLimit } });
          }
          push(t + 10, { type: "session.state", payload: { status: "paused", pausedReason: beat.reason ?? "user" } });
        }
        t += 200;
        break;
      }
      case "line": {
        t += beat.gapMs ?? (isWatch ? paceMs : 0);
        const id = nextMsgId();
        const side = beat.side ?? participants.find((p) => p.characterId === beat.who)?.side ?? undefined;
        const forced = beat.forcedBy === "user_ask" || beat.forcedBy === "mention" || beat.forcedBy === "nudge";
        const reactions: ReactionSpec[] | undefined = beat.reactions
          ? Object.entries(beat.reactions).map(([characterId, emotion]) => ({
              characterId,
              emotion: emotion!,
              p: beat.reactionTiming?.[characterId]?.p ?? Math.round(rng.range(0.48, 0.86) * 100) / 100,
              ...(beat.reactionTiming?.[characterId]?.delayMs !== undefined ? { delayMs: beat.reactionTiming[characterId]!.delayMs } : {}),
            }))
          : undefined;
        const cited = beat.cites?.length || beat.retrieved?.length
          ? citeKnowledge(`${sp.msgKey}:${id}`, (beat.cites ?? []).map(chunkRef), (beat.retrieved ?? []).map(chunkRef), {
              query: beat.knowledgeQuery, trigger: "always",
            })
          : null;
        for (const c of cited?.citations ?? []) {
          if (!beat.text.includes(`[${c.n}]`)) throw new Error(`[seed-build] ${id}: marker [${c.n}] missing from text`);
        }
        const script = buildLineScript(
          {
            sessionId: sid,
            messageId: id,
            characterId: beat.who,
            text: beat.text,
            emotion: beat.emotion,
            message: {
              seq: msgSeq,
              kind: "chat",
              ...(debate ? { debate: { phase: debate.phase, round: debate.round, iteration: debate.iteration, ...(side ? { side } : {}) } } : {}),
              ...(forced ? { forcedSpeaker: true } : {}),
            },
            forcedBy: beat.forcedBy,
            routing: beat.candidates
              ? { question: "Who should answer?", selected: beat.who, candidates: beat.candidates, ...(beat.forcedBy ? { forcedBy: beat.forcedBy } : {}) }
              : undefined,
            listeners: cast.filter((c) => c !== beat.who),
            reactions: reactions ?? [],
            energyBefore: { current: energy[beat.who] ?? 1000, max: 1000 },
            period,
            historyTokens,
            emotionTiming: beat.emotionTiming ?? "before",
            contextInSession: beat.contextInSession,
            memoryRecalled: beat.memory,
            usageOverride: beat.usage,
            traceOverride: beat.trace,
            ...(cited ? { citations: cited.citations, knowledge: cited.knowledge } : {}),
          },
          timing, PRICING, rng,
        );
        if (beat.at) {
          anchorRelT = t + 100;
          anchorAt = beat.at;
        }
        for (const e of script.entries) push(t + e.t, e.item!);
        spent[beat.who] = (spent[beat.who] ?? 0) + script.spent;
        energy[beat.who] = script.energyAfter;
        if (beat.trace?.energy) anchors[beat.who] = { spentThrough: spent[beat.who], remaining: beat.trace.energy.remaining };
        historyTokens += script.usage.tokensOut;
        t += script.endMs;
        if (watch) {
          watch = { ...watch, turnsTaken: watch.turnsTaken + 1 };
          push(t + 30, { type: "watch.state", payload: { status: "playing", paceMs, turnsTaken: watch.turnsTaken, turnLimit: watch.turnLimit } });
        }
        t += timing.turnGapMs;
        break;
      }
    }
  }
  return { timeline, spent, anchors, anchorRelT, anchorAt };
}

export function compileScreenplay(sp: Screenplay, endEnergy: Record<string, number>): CompiledSession {
  const cast = sp.session.participants.map((p) => p.characterId);
  // Pass 1: measure spend and anchors.
  const first = run(sp, Object.fromEntries(cast.map((c) => [c, endEnergy[c] ?? 1000])));
  const start: Record<string, number> = {};
  for (const c of cast) {
    const a = first.anchors[c];
    start[c] = a ? a.remaining + a.spentThrough : (endEnergy[c] ?? 1000) + (first.spent[c] ?? 0);
  }
  // Pass 2: final timeline with the right starting energy.
  const second = run(sp, start);
  const startMs = second.anchorAt !== null && second.anchorRelT !== null
    ? Date.parse(second.anchorAt) - second.anchorRelT
    : Date.parse(sp.startAt);

  const ordered = second.timeline
    .map((x, i) => ({ ...x, i }))
    .sort((a, b) => a.t - b.t || a.i - b.i);
  const events: SessionEvent[] = ordered.map((x, i) => {
    let evt = x.evt;
    if (evt.type === "message") {
      evt = { type: "message", payload: { message: { ...evt.payload.message, createdAt: iso(startMs + x.t) } } };
    }
    return {
      id: `evt_${sp.evtKey}${pad(i + 1, 4)}`,
      sessionId: sp.session.id,
      seq: i + 1,
      at: iso(startMs + x.t),
      type: evt.type,
      payload: evt.payload,
    };
  });

  const createdAt = iso(startMs);
  const { initialState, ...rest } = sp.session;
  const base: Session = {
    ...rest,
    status: "active",
    state: initialState,
    costUsd: 0,
    messageCount: 0,
    createdAt,
    updatedAt: createdAt,
  };
  const final = reduceAll(initialRuntime(base), events);
  return { session: final.session, messages: orderedMessages(final), events, spent: second.spent };
}
