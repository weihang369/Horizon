"""The pacing and runtime table (session-runtime design D9): `seed/runtime.json`, emitted by the seed build from the
mock's `timing.config.ts` plus `scripts/seed-build/runtime.config.ts`, so the backend and the MockClient pace live
sessions from one committed table (`seed:check` guards it). Milliseconds stay milliseconds here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Timing:
    thinking_ms: float
    first_token_ms: float
    tokens_per_sec: float
    chars_per_token: int
    tokens_per_event: int
    turn_gap_ms: float
    reaction_delay_ms: tuple[float, float]
    reaction_chance: float
    emotion_timing: dict[str, float]
    late_emotion_ms: float
    debate_start_ms: float
    watch_start_ms: float
    greeting_ms: float
    face_check_ms: float = 300.0   # M9 (doc 13 W2; turn-plan-emotion D24): the scripted face check's delay


@dataclass(frozen=True)
class JobTiming:
    """The generation-job pacing from the same table (`timing.config.ts`, generation-jobs design D2)."""

    profile_draft_ms: float
    field_regenerate_ms: float
    portrait_ms: float
    portrait_parallel: int
    emotion_ms: float
    emotion_parallel: int
    sheet_ms: float
    song_ms: float
    job_tick_ms: float


@dataclass(frozen=True)
class ReplyCaps:
    """docs/ai/03 C4: a safety net about 1.5–2× the prompt's length target, chosen after the turn plan."""

    one_on_one: int
    group: int
    watch: int
    debate: dict[str, int]
    one_on_one_deep: int = 300

    def for_mode(self, mode: str, turn_length: str | None = None, *, deep: bool = False) -> int:
        if mode == "debate":
            return self.debate.get(turn_length or "medium", self.debate["medium"])
        if mode == "one_on_one" and deep:
            return self.one_on_one_deep   # a deep group turn keeps the group cap: group replies stay short
        return int(getattr(self, mode))


@dataclass(frozen=True)
class WindowSizes:
    """docs/ai/05 X2: the history window per mode, in `count_tokens`."""

    one_on_one: int = 6000
    group: int = 9000
    watch: int = 9000
    debate: int = 9000

    def for_mode(self, mode: str) -> int:
        return int(getattr(self, mode, self.group))

    def as_dict(self) -> dict[str, int]:
        return {"one_on_one": self.one_on_one, "group": self.group, "watch": self.watch, "debate": self.debate}

    @staticmethod
    def from_json(v: Any) -> WindowSizes:
        """An object per mode; an older seed's single int applies to every mode."""
        if isinstance(v, int | float):
            n = int(v)
            return WindowSizes(n, n, n, n)
        return WindowSizes(**{k: int(v[k]) for k in ("one_on_one", "group", "watch", "debate")})


@dataclass(frozen=True)
class LlmCall:
    """One row of `runtime.llm.calls` (docs/ai/03 C1)."""

    thinking: str            # off | low | high
    temperature: float | None
    output: str              # stream | text | json
    max_tokens: int | None = None

    @property
    def reasoning(self) -> dict[str, Any]:
        """C2: off → `{enabled: false}` (group A A3: 0 reasoning tokens); low / high → that effort."""
        return {"enabled": False} if self.thinking == "off" else {"effort": self.thinking}


@dataclass(frozen=True)
class RetrievalKnobs:
    """M5 (knowledge-memory-storage design D12, D13): hits per reply and the query-embedding wait. AI-stage tunables."""

    knowledge_k: int
    memory_k: int
    query_embed_wait_ms: float
    agent: AgentRetrieval | None = None


@dataclass(frozen=True)
class RecallKnobs:
    """M13 (docs/ai/09 M9; memory design D31–D35, D42): recall's search, Jev call 2 and tail. `t_recall` is in the bank."""

    pool: int = 10                # BM25 and dense lists per corpus
    per_corpus: int = 5           # at most this many from each corpus into the merge
    candidates: int = 6           # MMR's picks, each checked by Jev call 2
    mmr_lambda: float = 0.7
    keep: int = 3                 # kept at or above t_recall, by p
    fallback_keep: int = 2        # every answer missing: the top of the merged order, unscored
    check_ms: float = 1500.0      # each recall check's deadline from when it was sent
    tail_tokens: int = 400        # both recall headings together
    line_words: int = 60          # a line hit and the message before it, each

    @staticmethod
    def from_json(r: dict[str, Any]) -> RecallKnobs:
        return RecallKnobs(pool=int(r["pool"]), per_corpus=int(r["perCorpus"]), candidates=int(r["candidates"]),
                           mmr_lambda=float(r["mmrLambda"]), keep=int(r["keep"]), fallback_keep=int(r["fallbackKeep"]),
                           check_ms=float(r["checkMs"]), tail_tokens=int(r["tailTokens"]),
                           line_words=int(r["lineWords"]))


@dataclass(frozen=True)
class AgentRetrieval:
    """M12 (docs/ai/10 K5–K7, K15; doc 13 W12; rag D26): the `agent` deep path's knobs. The thresholds are in the
    question bank."""

    pool: int = 20
    candidates: int = 8
    block_tokens: int = 1400
    mmr_lambda: float = 1.0
    k: dict[str, int] = field(default_factory=lambda: {"one_on_one": 3, "group": 2, "watch": 2, "debate": 2})
    piece_target: int = 300
    piece_max: int = 400
    rewrite_ms: float = 1200.0
    deep_check_ms: float = 1500.0
    query_embed_wait_ms: float = 200.0   # rag 11.5: the agent path's own wait (naive and scripted keep theirs)
    recall: RecallKnobs = field(default_factory=RecallKnobs)   # M13 (memory D42)

    def k_for(self, mode: str) -> int:
        return int(self.k.get(mode, self.k["group"]))

    @staticmethod
    def from_json(a: dict[str, Any]) -> AgentRetrieval:
        k = a["k"]
        return AgentRetrieval(pool=int(a["pool"]), candidates=int(a["candidates"]), block_tokens=int(a["blockTokens"]),
                              mmr_lambda=float(a["mmrLambda"]),
                              k={"one_on_one": int(k["oneOnOne"]), "group": int(k["group"]), "watch": int(k["watch"]),
                                 "debate": int(k["debate"])},
                              piece_target=int(a["pieceTarget"]), piece_max=int(a["pieceMax"]),
                              rewrite_ms=float(a["rewriteMs"]), deep_check_ms=float(a["deepCheckMs"]),
                              query_embed_wait_ms=float(a["queryEmbedWaitMs"]),
                              recall=RecallKnobs.from_json(a["recall"]) if "recall" in a else RecallKnobs())


@dataclass(frozen=True)
class MemoryKnobs:
    """M13 (docs/ai/09 M1, M2, M4–M8; doc 13 W12; memory design D42): pause runs and the memory list. AI-stage
    tunables; the guard's `t_keep` lives in the question bank."""

    leave_grace_ms: float = 30000.0      # doc 09 M1 trigger 1: the session stream left this long starts a run
    max_concurrent: int = 2              # runs at once (never the reply slots)
    piece_tokens: int = 8000             # doc 09 M2: a longer stretch runs in pieces of this many tokens
    max_tries: int = 3                   # doc 09 M6: failed tries on one checkpoint before the piece is skipped
    block_tokens: int = 1000             # doc 09 M8: the memory list in system message 1
    half_life_days: float = 30.0         # recency = max(floor, 0.5 ** (days / half_life))
    recency_floor: float = 0.5
    mode_weight: dict[str, float] = field(default_factory=lambda: {
        "one_on_one": 1.0, "group": 1.0, "debate": 0.85, "watch": 0.7})   # D-71's down-weighting
    min_importance: float = 0.25         # doc 09 M4: an add under this is dropped
    dup_cosine: float = 0.85             # doc 09 M5 (phase 10): an add this close to a memory asks Jev "same fact?"

    def weight(self, mode: str | None) -> float:
        """The mode weight of a memory's source mode; a seed or unknown mode weighs 1.0."""
        return float(self.mode_weight.get(mode or "", 1.0))

    @staticmethod
    def from_json(m: dict[str, Any]) -> MemoryKnobs:
        w = m["modeWeight"]
        return MemoryKnobs(leave_grace_ms=float(m["leaveGraceMs"]), max_concurrent=int(m["maxConcurrent"]),
                           piece_tokens=int(m["pieceTokens"]), max_tries=int(m["maxTries"]),
                           block_tokens=int(m["blockTokens"]), half_life_days=float(m["halfLifeDays"]),
                           recency_floor=float(m["recencyFloor"]),
                           mode_weight={"one_on_one": float(w["oneOnOne"]), "group": float(w["group"]),
                                        "debate": float(w["debate"]), "watch": float(w["watch"])},
                           min_importance=float(m["minImportance"]), dup_cosine=float(m["dupCosine"]))


@dataclass(frozen=True)
class RuntimeKnobs:
    reply_max_tokens: ReplyCaps
    window_tokens: WindowSizes
    coalesce_max_chars: int
    coalesce_max_ms: float
    idle_release_ms: float
    prefetch_max: int
    llm_concurrency: int
    retrieval: RetrievalKnobs
    llm_calls: dict[str, LlmCall]
    switches: dict[str, bool] = field(default_factory=dict)   # M8: "persona.repeatHint", "context.voiceReminder"
    emotion_fade: frozenset[str] = frozenset({"surprised", "embarrassed"})   # M9 (docs/ai/06 E3; design D13)
    host_welcome_wait_ms: float = 3000.0   # M11 (doc 08 V6; debate D11): Start + this for the welcome
    host_banner_wait_ms: float = 1500.0    # every other host line: its banner + this
    memory: MemoryKnobs = field(default_factory=MemoryKnobs)   # M13 (memory D42)

    def switch(self, name: str) -> bool:
        """A dynamic-tail switch (docs/ai/04 P8, 05 X5; doc 13 W12): off unless the table turns it on."""
        return bool(self.switches.get(name, False))

    def llm(self, key: str) -> LlmCall:
        try:
            return self.llm_calls[key]
        except KeyError as e:
            raise KeyError(f"no runtime.llm.calls row {key!r}") from e


@dataclass(frozen=True)
class RuntimeConfig:
    timing: Timing
    runtime: RuntimeKnobs
    jobs: JobTiming

    @staticmethod
    def from_json(data: dict[str, Any]) -> RuntimeConfig:
        t = data["timing"]
        r = data["runtime"]
        caps = r["replyMaxTokens"]
        return RuntimeConfig(
            timing=Timing(
                thinking_ms=float(t["thinkingMs"]), first_token_ms=float(t["firstTokenMs"]),
                tokens_per_sec=float(t["tokensPerSec"]), chars_per_token=int(t["charsPerToken"]),
                tokens_per_event=int(t["tokensPerEvent"]), turn_gap_ms=float(t["turnGapMs"]),
                reaction_delay_ms=(float(t["reactionDelayMs"][0]), float(t["reactionDelayMs"][1])),
                reaction_chance=float(t["reactionChance"]),
                emotion_timing={str(k): float(v) for k, v in t["emotionTiming"].items()},
                late_emotion_ms=float(t["lateEmotionMs"]), debate_start_ms=float(t["debateStartMs"]),
                watch_start_ms=float(t["watchStartMs"]), greeting_ms=float(t["greetingMs"]),
                face_check_ms=float(t["faceCheckMs"])),
            runtime=RuntimeKnobs(
                reply_max_tokens=ReplyCaps(one_on_one=int(caps["one_on_one"]), group=int(caps["group"]),
                                           watch=int(caps["watch"]),
                                           debate={str(k): int(v) for k, v in caps["debate"].items()},
                                           one_on_one_deep=int(caps.get("one_on_one_deep", caps["one_on_one"]))),
                window_tokens=WindowSizes.from_json(r["windowTokens"]), coalesce_max_chars=int(r["coalesce"]["maxChars"]),
                coalesce_max_ms=float(r["coalesce"]["maxMs"]), idle_release_ms=float(r["idleReleaseMs"]),
                prefetch_max=int(r["prefetchMax"]), llm_concurrency=int(r["llmConcurrency"]),
                retrieval=RetrievalKnobs(knowledge_k=int(r["retrieval"]["knowledgeK"]),
                                         memory_k=int(r["retrieval"]["memoryK"]),
                                         query_embed_wait_ms=float(r["retrieval"]["queryEmbedWaitMs"]),
                                         agent=AgentRetrieval.from_json(r["retrieval"]["agent"])),
                llm_calls={str(k): LlmCall(thinking=str(v["thinking"]),
                                           temperature=None if v.get("temperature") is None else float(v["temperature"]),
                                           output=str(v["output"]),
                                           max_tokens=int(v["maxTokens"]) if v.get("maxTokens") is not None else None)
                           for k, v in ((r.get("llm") or {}).get("calls") or {}).items()},
                switches={"persona.repeatHint": bool((r.get("persona") or {}).get("repeatHint", False)),
                          "persona.moodLine": bool((r.get("persona") or {}).get("moodLine", False)),   # M9 D40
                          "context.voiceReminder": bool((r.get("context") or {}).get("voiceReminder", False))},
                emotion_fade=frozenset(str(x) for x in r["emotion"]["fade"]),
                host_welcome_wait_ms=float(r["debate"]["hostWelcomeWaitMs"]),
                host_banner_wait_ms=float(r["debate"]["hostBannerWaitMs"]),
                memory=MemoryKnobs.from_json(r["memory"])),
            jobs=JobTiming(
                profile_draft_ms=float(t["profileDraftMs"]), field_regenerate_ms=float(t["fieldRegenerateMs"]),
                portrait_ms=float(t["portraitMs"]), portrait_parallel=int(t["portraitParallel"]),
                emotion_ms=float(t["emotionMs"]), emotion_parallel=int(t["emotionParallel"]), sheet_ms=float(t["sheetMs"]),
                song_ms=float(t["songMs"]), job_tick_ms=float(t["jobTickMs"])))


def load_runtime_config(seed_dir: Path) -> RuntimeConfig:
    doc = json.loads((seed_dir / "runtime.json").read_text(encoding="utf-8"))
    return RuntimeConfig.from_json(doc["data"])
