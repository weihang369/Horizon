"""Naive creation ports (generation-jobs design D9; ai-ports "Profile drafter", "Image generator").

- `NaiveDrafter`: one DeepSeek JSON-mode call (`response_format: json_object`, the schema in the system prompt)
  labelled `profile`, validated against the contract (an age under 18, a missing field or a bad palette fails the task, retryably). The
  draft's `profile` task makes the call; the other three draft tasks apply parts of the stored answer at $0.
- `NaiveImageGenerator`: Seedream 5.0 Flash (D-61) through `generate_image` at 3:4 and 1K, `n: 1`. Edits, blinks and
  tweaks send the locked base original as their only reference image (a data URL).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from horizon.ai.ports import ImageJob, PaidHooks
from horizon.ai.scripted.ports import AiDeps
from horizon.contract.validate import ContractSchema
from horizon.gateway.chat import ChatRequest, ChatResult
from horizon.gateway.context import CallContext
from horizon.gateway.errors import ProviderError
from horizon.gateway.images import ImageResult
from horizon.storage.images import data_url

LATENCY_MS = {"base": 17_000.0, "edit": 8_000.0, "sheet": 17_000.0}   # the D-61 run's figures
DRAFT_LATENCY_MS = 8_000.0   # measured on DeepSeek in the 2026-10-06 live run (7–8 s)
MAX_TOKENS = 2_400           # a whole draft measured 1,229 tokens: 1,200 cut every draft off mid-JSON
FIELD_MAX_TOKENS = 1_200     # one rewritten field
SCHEMA_PREFIX = "\nReturn only a JSON object that matches this JSON Schema (every property is required):\n"
FIELDS = ("tagline", "greeting", "backstory", "goals")

SYSTEM = ("You are Horizon's character drafter. From a one-line seed you write ONE original adult character (18 or "
          "older) as JSON that matches the schema exactly. Keep it grounded and safe for work: no real people, no "
          "minors, no explicit content. Expert characters are advisory: their boundaries say they inform but don't "
          "replace a professional. Write the appearance as plain visual facts an illustrator can draw.")


def _str(**kw: Any) -> dict[str, Any]:
    return {"type": "string", **kw}


def _arr(items: dict[str, Any], **kw: Any) -> dict[str, Any]:
    return {"type": "array", "items": items, **kw}


def _obj(props: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


def draft_schema(palette_ids: Sequence[str]) -> dict[str, Any]:
    """The JSON schema sent in the system prompt, built from the contract's `CharacterProfile`, `Appearance.attributes`,
    the shipped palettes and `SongBrief`: every property required, no extras, and every contract limit restated (a test
    keeps them in step), so the model is told each limit `parse_draft` enforces."""
    s = _str()
    profile = _obj({
        "name": _str(minLength=1), "role": _str(minLength=1), "age": {"type": "integer", "minimum": 18}, "pronouns": s,
        "tagline": _str(maxLength=80),
        "personality": _obj({"summary": s, "traits": _arr(s, minItems=3, maxItems=8)}), "backstory": s,
        "speakingStyle": _obj({"summary": s, "tone": s, "formality": _str(enum=["casual", "neutral", "formal"]),
                               "quirks": _arr(s), "catchphrases": _arr(s)}),
        "expertise": _arr(s), "goals": s, "boundaries": _arr(s), "greeting": s})
    attributes = _obj({
        "body": _obj({"ageBand": _str(enum=["young_adult", "adult", "middle_aged", "senior"]), "build": s, "height": s,
                      "skinTone": s}),
        "face": _obj({"shape": s, "baseline": _str(enum=["soft", "neutral", "sharp"]), "marks": _arr(s)}),
        "eyes": _obj({"shape": s, "color": s, "glasses": _str(enum=["none", "round", "square", "half_rim"])}),
        "hair": _obj({"length": s, "style": s, "color": s, "fringe": s}),
        "outfit": _obj({"archetype": s, "primaryColor": _str(pattern="^#[0-9A-Fa-f]{6}$"),
                        "secondaryColor": _str(pattern="^#[0-9A-Fa-f]{6}$")}),
        "accessories": _arr(s, maxItems=3), "vibe": _arr(s, maxItems=2)})
    brief = _obj({"genres": _arr(s), "moods": _arr(s), "bpm": {"type": "integer", "minimum": 60, "maximum": 160},
                  "instruments": _arr(s), "vibe": s})
    return _obj({"profile": profile, "attributes": attributes, "appearanceSummary": s,
                 "paletteId": _str(enum=list(palette_ids)), "advisory": {"type": "boolean"}, "brief": brief})


def parse_draft(content: str, schema: ContractSchema, palette_ids: Sequence[str]) -> dict[str, Any]:
    """The model's JSON → a contract-valid draft, or a retryable `provider_error` (nothing is applied)."""
    try:
        d = json.loads(content)
    except ValueError as e:
        raise ProviderError("provider_error", "The drafter returned something that isn't JSON.") from e
    if not isinstance(d, dict):
        raise ProviderError("provider_error", "The drafter returned something that isn't a draft.")
    missing = [k for k in ("profile", "attributes", "appearanceSummary", "paletteId", "advisory", "brief") if k not in d]
    if missing:
        raise ProviderError("provider_error", f"The draft is missing {', '.join(missing)}.")
    profile = d["profile"]
    if not isinstance(profile, dict) or not isinstance(profile.get("age"), int) or profile["age"] < 18:
        raise ProviderError("provider_error", "The draft must describe an adult (18 or older).")
    problems = schema.errors("CharacterProfile", profile)
    problems += schema.errors("SongBrief", d["brief"])
    problems += schema.errors("Appearance", {"attributes": d["attributes"], "appearanceSummary": d["appearanceSummary"],
                                             "candidates": [], "stylePresetId": "style_horizon_anime",
                                             "stylePresetVersion": 1})
    if d["paletteId"] not in palette_ids:
        problems.append(f"paletteId {d['paletteId']!r} is not a shipped palette")
    if not isinstance(d["advisory"], bool):
        problems.append("advisory must be true or false")
    if problems:
        raise ProviderError("provider_error", "The draft doesn't match the character format: " + "; ".join(problems[:3]))
    return d


class NaiveDrafter:
    shared_call = True

    def __init__(self, deps: AiDeps, schema: Callable[[], ContractSchema], palette_ids: Callable[[], Sequence[str]]) -> None:
        self.deps = deps
        self.schema = schema
        self.palette_ids = palette_ids

    def expected_ms(self, duration_ms: float) -> float:
        return DRAFT_LATENCY_MS

    @staticmethod
    def _request(model: str, user: str, schema: dict[str, Any], max_tokens: int) -> ChatRequest:
        """JSON mode, not strict `json_schema`: DeepSeek's own endpoint has no structured outputs, so under
        `require_parameters` the pinned provider was always skipped for a fallback (45–99 s, against DeepSeek's 7–8 s,
        in the 2026-10-06 live run). `parse_draft` still checks every answer against the contract."""
        system = SYSTEM + SCHEMA_PREFIX + json.dumps(schema, separators=(",", ":"))
        return ChatRequest(model=model, max_tokens=max_tokens, reasoning={"enabled": False},
                           messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                           response_format={"type": "json_object"})

    async def draft(self, ctx: CallContext, *, seed_prompt: str, intent: str, cost_usd: float, duration_ms: float,
                    model: str, hooks: PaidHooks) -> dict[str, Any]:
        ids = list(self.palette_ids())
        req = self._request(model, f"Seed: {seed_prompt}\nIntent: {intent}", draft_schema(ids), MAX_TOKENS)
        parsed: dict[str, Any] = {}

        async def after(r: ChatResult) -> None:
            parsed.update(parse_draft(r.content, self.schema(), ids))  # invalid → the row is still recorded, then raise
            if hooks.after_response is not None:
                await hooks.after_response(parsed)

        await self.deps.gateway().chat_complete(req, ctx, before_send=hooks.before_send, after_response=after,
                                                commit_with=hooks.commit_with)
        return parsed

    async def regenerate_field(self, ctx: CallContext, *, profile: Mapping[str, Any], field: str, attempt: int,
                               cost_usd: float, duration_ms: float, model: str, hooks: PaidHooks) -> dict[str, Any]:
        if field not in FIELDS:
            return {field: profile.get(field)} if field in profile else {}
        schema = _obj({field: _str(maxLength=80) if field == "tagline" else _str()})
        user = (f"Character: {json.dumps(dict(profile), ensure_ascii=False)[:4000]}\nRewrite only the field "
                f"{field!r}, in the same voice, as JSON.")
        out: dict[str, Any] = {}

        async def after(r: ChatResult) -> None:
            try:
                value = json.loads(r.content).get(field)
            except (ValueError, AttributeError) as e:
                raise ProviderError("provider_error", "The drafter returned something that isn't JSON.") from e
            if not isinstance(value, str) or not value.strip():
                raise ProviderError("provider_error", f"The drafter returned no {field}.")
            out[field] = value.strip()
            if hooks.after_response is not None:
                await hooks.after_response(out)

        await self.deps.gateway().chat_complete(self._request(model, user, schema, FIELD_MAX_TOKENS), ctx,
                                                before_send=hooks.before_send, after_response=after,
                                                commit_with=hooks.commit_with)
        return out


class NaiveImageGenerator:
    name = "naive"

    def __init__(self, deps: AiDeps) -> None:
        self.deps = deps

    def expected_ms(self, job: ImageJob) -> float:
        return LATENCY_MS.get(job.mode, LATENCY_MS["edit"])

    async def generate(self, ctx: CallContext, job: ImageJob, hooks: PaidHooks) -> bytes:
        refs = [data_url(job.reference)] if job.mode == "edit" and job.reference is not None else None
        if job.mode == "edit" and refs is None:
            raise ProviderError("provider_error", "This edit needs a locked base portrait.")

        async def after(r: ImageResult) -> None:
            if hooks.after_response is not None:
                await hooks.after_response(r.images[0])

        result = await self.deps.gateway().generate_image(
            ctx, model=job.model, prompt=job.prompt, kind=job.price_kind, refs=refs, resolution="1K",
            aspect_ratio=job.aspect_ratio, before_send=hooks.before_send, after_response=after,
            commit_with=hooks.commit_with)
        return result.images[0]
