"""The pacing and runtime table (session-runtime design D9): `seed/runtime.json`, emitted by the seed build from the
mock's `timing.config.ts` plus `scripts/seed-build/runtime.config.ts`, so the backend and the MockClient pace live
sessions from one committed table (`seed:check` guards it). Milliseconds stay milliseconds here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
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
    one_on_one: int
    group: int
    watch: int
    debate: dict[str, int]

    def for_mode(self, mode: str, turn_length: str | None = None) -> int:
        if mode == "debate":
            return self.debate.get(turn_length or "medium", self.debate["medium"])
        return int(getattr(self, mode))


@dataclass(frozen=True)
class RetrievalKnobs:
    """M5 (knowledge-memory-storage design D12, D13): hits per reply and the query-embedding wait. AI-stage tunables."""

    knowledge_k: int
    memory_k: int
    query_embed_wait_ms: float


@dataclass(frozen=True)
class RuntimeKnobs:
    reply_max_tokens: ReplyCaps
    window_tokens: int
    coalesce_max_chars: int
    coalesce_max_ms: float
    idle_release_ms: float
    prefetch_max: int
    llm_concurrency: int
    retrieval: RetrievalKnobs


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
                watch_start_ms=float(t["watchStartMs"]), greeting_ms=float(t["greetingMs"])),
            runtime=RuntimeKnobs(
                reply_max_tokens=ReplyCaps(one_on_one=int(caps["one_on_one"]), group=int(caps["group"]),
                                           watch=int(caps["watch"]),
                                           debate={str(k): int(v) for k, v in caps["debate"].items()}),
                window_tokens=int(r["windowTokens"]), coalesce_max_chars=int(r["coalesce"]["maxChars"]),
                coalesce_max_ms=float(r["coalesce"]["maxMs"]), idle_release_ms=float(r["idleReleaseMs"]),
                prefetch_max=int(r["prefetchMax"]), llm_concurrency=int(r["llmConcurrency"]),
                retrieval=RetrievalKnobs(knowledge_k=int(r["retrieval"]["knowledgeK"]),
                                         memory_k=int(r["retrieval"]["memoryK"]),
                                         query_embed_wait_ms=float(r["retrieval"]["queryEmbedWaitMs"]))),
            jobs=JobTiming(
                profile_draft_ms=float(t["profileDraftMs"]), field_regenerate_ms=float(t["fieldRegenerateMs"]),
                portrait_ms=float(t["portraitMs"]), portrait_parallel=int(t["portraitParallel"]),
                emotion_ms=float(t["emotionMs"]), emotion_parallel=int(t["emotionParallel"]), sheet_ms=float(t["sheetMs"]),
                song_ms=float(t["songMs"]), job_tick_ms=float(t["jobTickMs"])))


def load_runtime_config(seed_dir: Path) -> RuntimeConfig:
    doc = json.loads((seed_dir / "runtime.json").read_text(encoding="utf-8"))
    return RuntimeConfig.from_json(doc["data"])
