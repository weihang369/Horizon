"""Task plans per job kind (generation-jobs design D2): a pure port of the MockClient's `planTasks`/`estimateJob`.

Each task carries its paced duration (the shared timing table), its estimate (the committed price table) and the
price kind its image call is billed at. One exception to the mock, by decision D-83: a theme song is the procedural
theme while OpenRouter lists no music model, so it is estimated (and costs) $0.

`task_spec()` rebuilds one task's plan from the job kind and the task type, so recovery, retry and the test-mode
overlay jobs (stored without an input) get the same durations and prices as a fresh start.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from horizon.domain.pricing import round6
from horizon.domain.runtime_config import JobTiming

LEAN_EMOTIONS = ("happy", "sad", "angry")
ALL_EMOTIONS = ("happy", "sad", "angry", "surprised", "thinking", "embarrassed")
PROFILE_PARTS = ("profile", "appearance_summary", "palette_pick", "song_brief")
IMAGE_TYPES = frozenset({"portrait_candidate", "emotion_image", "blink_frame", "expression_sheet"})
JOB_KINDS = ("profile_draft", "profile_regenerate", "portrait_candidates", "portrait_tweak", "emotion_set",
             "emotion_regenerate", "song")


@dataclass(frozen=True)
class TaskPlan:
    type: str
    emotion: str | None
    est_usd: float
    duration_ms: float
    price_kind: str | None      # the `pricing.generation` key this task is billed at (None: free)
    category: str               # the ledger category: profile | image | music


@dataclass(frozen=True)
class JobPlan:
    tasks: list[TaskPlan]
    parallel: int

    @property
    def estimate(self) -> float:
        return round6(sum(t.est_usd for t in self.tasks))


def task_spec(kind: str, type_: str, emotion: str | None, *, sheet_job: bool, prices: Mapping[str, float],
              timing: JobTiming) -> TaskPlan:
    g = prices
    if type_ in PROFILE_PARTS:
        ms = timing.field_regenerate_ms if kind == "profile_regenerate" else timing.profile_draft_ms / 4
        return TaskPlan(type_, None, g["profileDraft"] / 4, ms, "profileDraft", "profile")
    if type_ == "portrait_candidate":
        price = "tweak" if kind == "portrait_tweak" else "portrait"
        return TaskPlan(type_, None, g[price], timing.portrait_ms, price, "image")
    if type_ == "expression_sheet":
        return TaskPlan(type_, None, g["expressionSheet"], timing.sheet_ms, "expressionSheet", "image")
    if type_ == "emotion_image":
        if sheet_job:  # sliced from the sheet: no call of its own
            return TaskPlan(type_, emotion, 0.0, 0.0, None, "image")
        return TaskPlan(type_, emotion, g["emotionEdit"], timing.emotion_ms, "emotionEdit", "image")
    if type_ == "blink_frame":
        return TaskPlan(type_, None, g["blinkFrame"], timing.emotion_ms, "blinkFrame", "image")  # the neutral blink
    if type_ == "theme_song":
        return TaskPlan(type_, None, 0.0, timing.song_ms, None, "music")  # D-83: the procedural theme is free
    raise ValueError(f"unknown task type {type_!r}")


def parallel_for(kind: str, timing: JobTiming, *, sheet_job: bool = False) -> int:
    if kind == "portrait_candidates":
        return timing.portrait_parallel
    if kind == "emotion_set" and not sheet_job:
        return timing.emotion_parallel
    return 1


def plan(job_input: Mapping[str, Any], *, lean: bool, prices: Mapping[str, float], timing: JobTiming) -> JobPlan:
    kind = str(job_input["kind"])
    emotions: Sequence[str] | None = job_input.get("emotions")
    sheet = kind == "emotion_set" and job_input.get("technique") == "expression_sheet"

    def mk(type_: str, emotion: str | None = None) -> TaskPlan:
        return task_spec(kind, type_, emotion, sheet_job=sheet, prices=prices, timing=timing)

    if kind == "profile_draft":
        tasks = [mk(t) for t in PROFILE_PARTS]
    elif kind == "profile_regenerate":
        tasks = [mk("profile")]
    elif kind == "portrait_candidates":
        tasks = [mk("portrait_candidate") for _ in range(1 if lean else 2)]
    elif kind == "portrait_tweak":
        tasks = [mk("portrait_candidate")]
    elif kind == "emotion_set":
        chosen = list(emotions) if emotions else list(LEAN_EMOTIONS if lean else ALL_EMOTIONS)
        if sheet:
            tasks = [mk("expression_sheet"), *(mk("emotion_image", e) for e in chosen)]
        else:
            tasks = [mk("emotion_image", e) for e in chosen]
            if not lean:
                tasks.append(mk("blink_frame"))
    elif kind == "emotion_regenerate":
        tasks = [mk("emotion_image", e) for e in (list(emotions) if emotions else ["happy"])]
    elif kind == "song":
        tasks = [mk("theme_song")]
    else:
        raise ValueError(f"unknown job kind {kind!r}")
    return JobPlan(tasks=tasks, parallel=parallel_for(kind, timing, sheet_job=sheet))
