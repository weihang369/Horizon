// Group engine (MULTI-02/03/04, ENG-04 AC3): mentions first, then up to 2 by score (Auto), everyone, or mentioned
// only. Exhausted or muted characters are skipped with a system note; routing candidates go into the trace. Owner: EE.
import type { GroupConfig } from "../../contract/types";
import { decisionCostUsd, ROUTE_DECISION_TOKENS } from "../../domain/cost";
import type { EngineHost } from "./host";
import { asleepNote, enqueue, isAsleep, speakThen, userMessage } from "./host";

type Skip = { characterId: string; reason: "exhausted" | "muted" | "archived" };

function policyOf(h: EngineHost, sid: string): GroupConfig["responderPolicy"] {
  const cfg = h.live(sid).state.session.config as GroupConfig | null;
  return cfg?.responderPolicy ?? "auto";
}

/** Run a list of speakers sequentially as one queued task. */
export function runSpeakers(h: EngineHost, sid: string, speakers: string[], prompt: string, opts: { forced?: Set<string>; forcedBy?: "mention" | "nudge"; candidates?: { characterId: string; p: number }[]; skipped?: Skip[] } = {}): void {
  const live = h.live(sid);
  enqueue(live, (done) => {
    let i = 0;
    const next = () => {
      if (i >= speakers.length) return done();
      const cid = speakers[i++];
      if (isAsleep(h, cid)) {
        asleepNote(h, sid, cid, !opts.forced?.has(cid));
        return next();
      }
      const forced = opts.forced?.has(cid);
      speakThen(h, sid, cid, {
        prompt,
        forcedBy: forced ? opts.forcedBy ?? "mention" : undefined,
        message: forced ? { forcedSpeaker: true } : undefined,
        skipped: i === 1 ? opts.skipped : undefined,
        routing: opts.candidates
          ? { question: "Who should answer?", selected: cid, candidates: opts.candidates, ...(forced ? { forcedBy: opts.forcedBy ?? ("mention" as const) } : {}), ...(opts.skipped?.length ? { skipped: opts.skipped } : {}) }
          : undefined,
      }, () => next());
    };
    next();
  });
}

function pickResponders(h: EngineHost, sid: string, text: string, mentions: string[]): { speakers: string[]; forced: Set<string>; candidates: { characterId: string; p: number }[]; skipped: Skip[] } {
  const live = h.live(sid);
  const s = live.state.session;
  const rng = h.rng(`${sid}:route:${live.turn}`);
  const policy = policyOf(h, sid);
  const skipped: Skip[] = [];
  const eligible: string[] = [];
  for (const p of s.participants) {
    if (p.mutedByUser) skipped.push({ characterId: p.characterId, reason: "muted" });
    else if (isAsleep(h, p.characterId) && !mentions.includes(p.characterId)) skipped.push({ characterId: p.characterId, reason: "exhausted" });
    else eligible.push(p.characterId);
  }
  const lower = text.toLowerCase();
  const candidates = eligible
    .filter((c) => !mentions.includes(c))
    .map((cid) => {
      const name = h.db.characters[cid]?.profile.name.toLowerCase() ?? "";
      const bonus = name.split(" ").some((w) => w.length > 2 && lower.includes(w)) ? 0.3 : 0;
      return { characterId: cid, p: Math.round(Math.min(0.97, rng.range(0.2, 0.75) + bonus) * 100) / 100 };
    })
    .sort((a, b) => b.p - a.p);
  const forced = new Set(mentions.filter((m) => s.participants.some((p) => p.characterId === m)));
  let rest: string[] = [];
  if (policy === "everyone") rest = candidates.map((c) => c.characterId);
  else if (policy === "auto") rest = candidates.slice(0, Math.max(0, 2 - forced.size)).map((c) => c.characterId);
  return { speakers: [...forced, ...rest], forced, candidates, skipped };
}

export function send(h: EngineHost, sid: string, text: string, mentions: string[] = []): void {
  h.emit(sid, { type: "message", payload: { message: userMessage(h, sid, text) } });
  const r = pickResponders(h, sid, text, mentions);
  // The Jev routing question (TurnTrace.calls "route") is a paid decision call.
  if (r.candidates.length) h.charge(sid, "decision", decisionCostUsd(ROUTE_DECISION_TOKENS, h.pricing.decision));
  if (!r.speakers.length) {
    if (policyOf(h, sid) === "mentioned") return; // the UI shows "Mention someone with @…"
  }
  runSpeakers(h, sid, r.speakers, text, r);
}

export function everyoneAnswer(h: EngineHost, sid: string): void {
  const s = h.live(sid).state.session;
  const last = [...h.live(sid).state.order].reverse().map((id) => h.live(sid).state.messages[id]).find((m) => m?.author.type === "user")?.content ?? "";
  runSpeakers(h, sid, s.participants.filter((p) => !p.mutedByUser).map((p) => p.characterId), last);
}

export function nextSpeaker(h: EngineHost, sid: string, cid?: string): void {
  const live = h.live(sid);
  const s = live.state.session;
  let pick = cid;
  if (!pick) {
    const lastSpeaker = [...live.state.order].reverse().map((id) => live.state.messages[id]).find((m) => m?.author.type === "character")?.author.characterId;
    const pool = s.participants.filter((p) => !p.mutedByUser && p.characterId !== lastSpeaker && !isAsleep(h, p.characterId));
    pick = pool.length ? h.rng(`${sid}:next:${live.turn}`).pick(pool).characterId : undefined;
  }
  if (!pick) return;
  runSpeakers(h, sid, [pick], "", { forced: cid ? new Set([cid]) : undefined, forcedBy: "nudge" });
}
