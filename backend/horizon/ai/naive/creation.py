"""Naive creation ports (generation-jobs design D9; ai-ports "Profile drafter", "Image generator").

- `NaiveDrafter`: one DeepSeek JSON-mode call (`response_format: json_object`, the schema in the system prompt)
  labelled `profile`, validated against the contract (an age under 18, a missing field or a bad palette fails the task, retryably). The
  draft's `profile` task makes the call; the other three draft tasks apply parts of the stored answer at $0.
  JSON calls go through `complete_json` (docs/ai/03 C7, §5; ai-foundation design D19): the prompt asks for single
  quotes inside text values; an answer that doesn't parse or validate gets the free local quote repair, then ONE paid
  retry with the error appended (the cached prefix unchanged); a second failure is the task's retryable failure. Only
  parse or validation failures retry: timeouts, transport errors, refusals and budget errors keep their handling.
- `NaiveImageGenerator`: Seedream 5.0 Flash (D-61) through `generate_image` at 3:4 and 1K, `n: 1`. Edits, blinks and
  tweaks send the locked base original as their only reference image (a data URL).
- `NaiveSong`: Lyria 3 Clip (D-87) through `generate_music`: one instrumental prompt compiled from the brief, a
  30-second MP3 back. Audio that isn't a usable MP3 fails as a billed `provider_error` before it is stored; the job
  worker then falls back to the procedural theme (creation-followups design D7).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from typing import Any

from horizon.ai.jsonrepair import repair_json_quotes
from horizon.ai.llm import llm_request
from horizon.ai.ports import DraftWorld, ImageJob, PaidHooks, SongJob
from horizon.ai.scripted.ports import AiDeps
from horizon.contract.validate import ContractSchema
from horizon.gateway.chat import ChatRequest, ChatResult
from horizon.gateway.context import CallContext
from horizon.gateway.errors import ProviderError
from horizon.gateway.images import ImageResult
from horizon.gateway.music import MusicResult
from horizon.services import theme
from horizon.storage.audio import MAX_SONG_BYTES, is_mp3
from horizon.storage.images import data_url

LATENCY_MS = {"base": 17_000.0, "edit": 8_000.0, "sheet": 17_000.0}   # the D-61 run's figures
NAIVE_SONG_LATENCY_MS = 17_000.0   # measured in the 2026-10-08 live run: one 28 s clip in 16.3 s (design D9)
DRAFT_LATENCY_MS = 8_000.0   # measured on DeepSeek in the 2026-10-06 live run (7–8 s)
MAX_TOKENS = 2_400           # a whole draft measured 1,229 tokens: 1,200 cut every draft off mid-JSON
FIELD_MAX_TOKENS = 1_200     # one rewritten field
SCHEMA_PREFIX = "\nReturn only a JSON object that matches this JSON Schema (every property is required):\n"
# group A A3: a nickname in unescaped double quotes broke 1 draft in 20, and its retry made the same mistake.
QUOTE_RULE = "\nInside JSON text values, use single quotes for any quotation; never use a double quote inside a value."
FIELDS = ("tagline", "greeting", "backstory", "goals")

SYSTEM = ("You are Horizon's character drafter. From a one-line seed you write ONE original adult character (18 or "
          "older) as JSON that matches the schema exactly. Keep it grounded and safe for work: no real people, no "
          "minors, no explicit content. Expert characters are advisory: their boundaries say they inform but don't "
          "replace a professional. Write the appearance as plain visual facts an illustrator can draw.")
# docs/ai/04 P11 (persona-context design D17): names, originality, a concrete life, an audible voice, plain speech.
# M15 (images-music 8.13; m14.md finding 7): the originality rule also bars the source's catchphrases and speech.
STOCK_NAMES = ("Elara", "Kael", "Seraphina", "Lyra", "Aria", "Voss", "Thorne")
RULES = (
    "\nRules:"
    "\n- Give a name that fits the role and the culture of the setting. Never use a name already used in this world, "
    "and avoid stock AI names (" + ", ".join(STOCK_NAMES) + ")."
    "\n- Characters are original. If the seed asks for a real person or an existing fictional character, write an "
    "original character of the same general type, with a new name. A new name is not enough: never reuse their "
    "catchphrases, signature lines or recognisable way of speaking (an unusual word order, a verbal tic); give the "
    "character a voice of their own."
    "\n- Give a concrete backstory with specific details and one flaw."
    "\n- Describe the speaking style as habits you could hear (sentence length, words they use), not adjectives."
    "\n- The greeting is at most 2 short lines. Give 2-3 example lines that show the voice and differ from the greeting."
    "\n- The greeting and example lines are plain speech only: no *actions* or stage directions."
    "\n- relationshipToUser: for a companion, who the user is to them, fitting the user described below; for any other "
    "intent, an empty string."
)
# docs/ai/03 C7: the schema and ONE example (never built before M8). Invented names, no seed-world or stock names.
EXAMPLE_SEED = "a night-shift radio host who misses her hometown"
EXAMPLE = {
    "profile": {
        "name": "Bao Ngoc Tran", "role": "Night-shift radio host", "age": 34, "pronouns": "she/her",
        "tagline": "On air until the sun comes up.",
        "personality": {"summary": "Warm and wry, a good listener who hides homesickness behind jokes.",
                        "traits": ["warm", "wry", "observant", "restless"]},
        "backstory": ("Grew up above her parents' noodle stall in Hue, moved to the city for a radio job at 23, and has "
                      "hosted the 1 a.m. call-in show for six years. She still keeps her grandmother's tin radio on "
                      "the studio desk. Flaw: she says yes to every caller and never to herself."),
        "speakingStyle": {"summary": "Short sentences, late-night pauses, asks one question then lets you talk.",
                          "tone": "warm", "formality": "casual",
                          "quirks": ["names the time before she answers", "uses food words for feelings"],
                          "catchphrases": ["Still with me?"]},
        "expertise": ["late-night radio", "listening", "Vietnamese home cooking"],
        "goals": "Save enough to open a tiny station back home.",
        "boundaries": ["Keeps things kind and safe for work."],
        "greeting": "It's 1 a.m. and you're up too. Good.",
        "exampleLines": ["That sounds like a cold-rice kind of day.", "Two minutes past three. Tell me the rest."],
        "relationshipToUser": "her favourite regular caller",
    },
    "attributes": {
        "body": {"ageBand": "adult", "build": "slim", "height": "average", "skinTone": "light tan"},
        "face": {"shape": "oval", "baseline": "soft", "marks": ["small mole under the left eye"]},
        "eyes": {"shape": "almond", "color": "dark brown", "glasses": "none"},
        "hair": {"length": "shoulder", "style": "loose with headphones on", "color": "black", "fringe": "side-swept"},
        "outfit": {"archetype": "casual", "primaryColor": "#2E3A59", "secondaryColor": "#F2C14E"},
        "accessories": ["studio headphones"], "vibe": ["warm", "night owl"],
    },
    "appearanceSummary": ("An adult woman with light tan skin and shoulder-length black hair under studio "
                          "headphones, dark brown eyes, a navy cardigan with a mustard scarf."),
    "paletteId": "pal_midnight_ink", "advisory": False,
    "brief": {"genres": ["lo-fi"], "moods": ["calm"], "bpm": 78, "instruments": ["piano", "vinyl crackle"],
              "vibe": "a quiet studio at 3 a.m."},
}
EXAMPLE_PREFIX = f'\nOne example of a complete answer (seed: "{EXAMPLE_SEED}", intent: companion):\n'


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
        "expertise": _arr(s), "goals": s, "boundaries": _arr(s), "greeting": s,
        "exampleLines": _arr(s, minItems=2, maxItems=3), "relationshipToUser": s})
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


class InvalidJson(ProviderError):
    """A JSON call's answer didn't parse or validate: the one failure `complete_json` retries."""

    def __init__(self, message: str) -> None:
        super().__init__("provider_error", message)



async def complete_json[T](gw: Any, req: ChatRequest, ctx: CallContext, parse: Callable[[str], T], hooks: PaidHooks) -> T:
    """docs/ai/03 C7 with group A's fix: parse → free quote repair → one paid retry (error appended) → failure.
    Each call is its own ledger row; the first call commits with the task's `commit_with` even when its answer is
    unusable, so the task's cost is the sum of both calls (the worker adds them up)."""
    out: dict[str, T] = {}
    failed: dict[str, str] = {}

    def read(content: str) -> T:
        try:
            return parse(content)
        except ProviderError as first:
            repaired = repair_json_quotes(content)
            if repaired == content:
                raise InvalidJson(first.message) from first
            try:
                return parse(repaired)
            except ProviderError:
                raise InvalidJson(first.message) from first

    async def after_first(r: ChatResult) -> None:
        try:
            out["v"] = read(r.content)
        except InvalidJson as e:
            failed["error"] = e.message   # billed; committed with the task, then retried once
            return
        if hooks.after_response is not None:
            await hooks.after_response(out["v"])

    async def after_retry(r: ChatResult) -> None:
        out["v"] = read(r.content)       # a second failure raises: the row is still recorded
        if hooks.after_response is not None:
            await hooks.after_response(out["v"])

    first = await gw.chat_complete(req, ctx, before_send=hooks.before_send, after_response=after_first,
                                   commit_with=hooks.commit_with)
    if not failed:
        return out["v"]
    retry = replace(req, messages=[*req.messages, {"role": "assistant", "content": first.content},
                                   {"role": "user", "content": f"That wasn't valid: {failed['error']} Reply again with "
                                                               "the whole JSON object only."}])
    await gw.chat_complete(retry, ctx, before_send=hooks.before_send, after_response=after_retry,
                           commit_with=hooks.commit_with)
    return out["v"]


# persona-context D33 (the user's choice after the paid drafter run): DeepSeek often leaves `personality` open, writes
# the rest of the profile inside it and ends one `}` short. A free structural repair runs before C7's paid retry.
TOP_KEYS = ("attributes", "appearanceSummary", "paletteId", "advisory", "brief")
PROFILE_KEYS = ("backstory", "speakingStyle", "expertise", "goals", "boundaries", "greeting", "exampleLines",
                "relationshipToUser")


def close_json(content: str) -> str:
    """`content` with its unclosed `{` and `[` closed at the end, in order (strings and escapes respected)."""
    stack: list[str] = []
    in_str = esc = False
    for ch in content:
        if in_str:
            esc, in_str = (False, True) if esc else (ch == "\\", ch != '"')
        elif ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]" and stack and stack[-1] == ch:
            stack.pop()
    return content if in_str or not stack else content.rstrip() + "".join(reversed(stack))


def hoist_draft(d: dict[str, Any]) -> dict[str, Any]:
    """Fields written one level too deep go back where the contract wants them (never overwriting one in place)."""
    profile = d.get("profile")
    if not isinstance(profile, dict):
        return d
    for k in TOP_KEYS:
        if k not in d and k in profile:
            d[k] = profile.pop(k)
    personality = profile.get("personality")
    if isinstance(personality, dict):
        for k in PROFILE_KEYS:
            if k not in profile and k in personality:
                profile[k] = personality.pop(k)
    return d


def load_draft(content: str) -> Any:
    """json.loads, then (D33) the closed-brackets text, then the first complete object of a text with extra closers."""
    for attempt in (content, close_json(content)):
        try:
            return json.loads(attempt)
        except ValueError:
            pass
    return json.JSONDecoder().raw_decode(content.strip())[0]


def parse_draft(content: str, schema: ContractSchema, palette_ids: Sequence[str]) -> dict[str, Any]:
    """The model's JSON → a contract-valid draft, or a retryable `provider_error` (nothing is applied)."""
    try:
        d = load_draft(content)
    except ValueError as e:
        raise ProviderError("provider_error", "The drafter returned something that isn't JSON.") from e
    if not isinstance(d, dict):
        raise ProviderError("provider_error", "The drafter returned something that isn't a draft.")
    d = hoist_draft(d)
    missing = [k for k in ("profile", "attributes", "appearanceSummary", "paletteId", "advisory", "brief") if k not in d]
    if missing:
        raise ProviderError("provider_error", f"The draft is missing {', '.join(missing)}.")
    profile = d["profile"]
    if isinstance(profile, dict) and not str(profile.get("relationshipToUser") or "").strip():
        profile.pop("relationshipToUser", None)   # P11: empty for non-companions, then omitted
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


def draft_user_message(seed_prompt: str, intent: str, world: DraftWorld | None) -> str:
    """P11: the seed and intent, then the world's name, the names already used in it and the You card."""
    lines = [f"Seed: {seed_prompt}", f"Intent: {intent}"]
    if world is not None:
        if world.name:
            lines.append(f"World: {world.name}")
        lines.append("Names already used here: " + (", ".join(world.names_in_use) if world.names_in_use else "none"))
        you = world.you or {}
        if you.get("displayName"):
            about = f" ({you['about']})" if you.get("about") else ""
            lines.append(f"The user: {you['displayName']}{about}")
    return "\n".join(lines)


class NaiveDrafter:
    shared_call = True

    def __init__(self, deps: AiDeps, schema: Callable[[], ContractSchema], palette_ids: Callable[[], Sequence[str]]) -> None:
        self.deps = deps
        self.schema = schema
        self.palette_ids = palette_ids

    def expected_ms(self, duration_ms: float) -> float:
        return DRAFT_LATENCY_MS

    @staticmethod
    def _request(model: str, user: str, schema: dict[str, Any], max_tokens: int, row: Any = None) -> ChatRequest:
        """JSON mode, not strict `json_schema`: DeepSeek's own endpoint has no structured outputs, so under
        `require_parameters` the pinned provider was always skipped for a fallback (45–99 s, against DeepSeek's 7–8 s,
        in the 2026-10-06 live run). `parse_draft` still checks every answer against the contract. The `profile`
        settings row gives thinking off and temperature 1.0 (docs/ai/03 C1)."""
        system = SYSTEM + RULES + SCHEMA_PREFIX + json.dumps(schema, separators=(",", ":")) + QUOTE_RULE
        if "profile" in schema.get("properties", {}):   # a whole draft: the one example (C7); a field rewrite needs none
            system += EXAMPLE_PREFIX + json.dumps(EXAMPLE, ensure_ascii=False, separators=(",", ":"))
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        if row is None:   # a bare AiDeps (unit tests): the same settings, spelled out
            return ChatRequest(model=model, max_tokens=max_tokens, temperature=1.0, reasoning={"enabled": False},
                               messages=messages, response_format={"type": "json_object"})
        return llm_request(row, model, messages, max_tokens=max_tokens, response_format={"type": "json_object"})

    async def draft(self, ctx: CallContext, *, seed_prompt: str, intent: str, cost_usd: float, duration_ms: float,
                    model: str, hooks: PaidHooks, world: DraftWorld | None = None) -> dict[str, Any]:
        ids = list(self.palette_ids())
        req = self._request(model, draft_user_message(seed_prompt, intent, world), draft_schema(ids), MAX_TOKENS,
                            self.deps.llm("profile"))
        return await complete_json(self.deps.gateway(), req, ctx, lambda c: parse_draft(c, self.schema(), ids), hooks)

    async def regenerate_field(self, ctx: CallContext, *, profile: Mapping[str, Any], field: str, attempt: int,
                               cost_usd: float, duration_ms: float, model: str, hooks: PaidHooks) -> dict[str, Any]:
        if field not in FIELDS:
            return {field: profile.get(field)} if field in profile else {}
        schema = _obj({field: _str(maxLength=80) if field == "tagline" else _str()})
        user = (f"Character: {json.dumps(dict(profile), ensure_ascii=False)[:4000]}\nRewrite only the field "
                f"{field!r}, in the same voice, as JSON.")
        if field == "greeting":   # P11: the same plain-speech and length rules as a whole draft
            user += (" At most 2 short lines of plain speech: no *actions*, no stage directions, and not an "
                     "assistant's offer of help.")
        def parse(content: str) -> dict[str, Any]:
            try:
                value = json.loads(content).get(field)
            except (ValueError, AttributeError) as e:
                raise ProviderError("provider_error", "The drafter returned something that isn't JSON.") from e
            if not isinstance(value, str) or not value.strip():
                raise ProviderError("provider_error", f"The drafter returned no {field}.")
            return {field: value.strip()}

        return await complete_json(self.deps.gateway(),
                                   self._request(model, user, schema, FIELD_MAX_TOKENS, self.deps.llm("profile")), ctx,
                                   parse, hooks)


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


def _listed(values: Any) -> str:
    return ", ".join(str(v).strip() for v in values if str(v).strip()) if isinstance(values, list) else ""


SONG_CONSTRAINTS = ("An original piece: do not imitate any named artist, band or existing song. "
                    "No vocals, no lyrics. A 30-second piece that loops cleanly.")


def song_prompt(brief: Mapping[str, Any]) -> str:
    """The instrumental prompt for one clip (creation-followups design D4): every brief value that is set, then the
    constraints. Deterministic, so the same brief always asks for the same piece. M15 (doc 12 I2; images-music D8): no
    title or name (it tells Lyria nothing musical, and "Taylor's Theme" would put a real name in the prompt), and the
    original-piece line before the vocals line."""
    return f"{song_brief_text(brief)} {SONG_CONSTRAINTS}"


def song_brief_text(brief: Mapping[str, Any]) -> str:
    """The part of `song_prompt` that varies with the brief: what the song check reads (M15, images-music 8.3). The
    constraint lines are ours and constant, so they can't carry a copy request; read with the brief, their "do not
    imitate any named artist" halved Jev's p on real copy requests (0.97–0.99 → 0.45–0.87, m15.md)."""
    parts = ["Instrumental theme music for a character."]
    for label, key in (("Genres", "genres"), ("Mood", "moods"), ("Instruments", "instruments")):
        if text := _listed(brief.get(key)):
            parts.append(f"{label}: {text}.")
    if isinstance(brief.get("bpm"), int | float):
        parts.append(f"Tempo: about {int(brief['bpm'])} BPM.")
    if vibe := str(brief.get("vibe") or "").strip():
        parts.append(f"Feel: {vibe}.")
    return " ".join(parts)


class NaiveSong:
    model = "lyria"   # the configured `models.music` travels on each SongJob
    paid = True

    def __init__(self, deps: AiDeps) -> None:
        self.deps = deps

    def expected_ms(self, duration_ms: float) -> float:
        return NAIVE_SONG_LATENCY_MS

    def theme(self, seed: str, brief: Mapping[str, Any], title: str | None) -> dict[str, Any]:
        return theme.theme_spec_from_brief(seed, brief, title)

    async def generate(self, ctx: CallContext, job: SongJob, hooks: PaidHooks) -> bytes:
        async def after(r: MusicResult) -> None:
            if len(r.audio) > MAX_SONG_BYTES or not is_mp3(r.audio):   # billed: the row is still recorded, then raise
                raise ProviderError("provider_error", "The music provider returned audio we couldn't use.")
            if hooks.after_response is not None:
                await hooks.after_response(r.audio)

        result = await self.deps.gateway().generate_music(
            ctx, model=job.model, prompt=song_prompt(job.brief), before_send=hooks.before_send,
            after_response=after, commit_with=hooks.commit_with)
        return result.audio
