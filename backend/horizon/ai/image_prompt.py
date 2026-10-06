"""The image prompt compiler (generation-jobs design D9; ai-ports "Image prompt compiler"). One deterministic class in
both AI profiles: the TESTING.md templates (A1 base, A2 emotion edit, A3 expression sheet) and the compiler rules in
its appendix, with the README's v2 fixes from the D-61 run:

1. the base expression follows `face.baseline` (soft → a faint warm smile; sharp → a composed, slightly intense gaze);
2. thinking is reworded (it read as suspicious);
3. angry has no flush (blush is for embarrassed only);
4. a compound hair colour keeps its base colour first ("chestnut hair with a soft pink tint", not "pink-tinted
   chestnut", which came out salmon pink).

Under 18 → no prompt and a `REFUSED` warning, so the task fails without a call. Golden fixtures for four seed
characters live in `tests/fixtures/image_prompt/` (Python only: the frontend has no compiler).
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

ADULT = "Adult character with adult proportions and a mature face."
COMPOSITION = ("Composition: single character, vertical 3:4 portrait, waist-up, centred, body turned slightly (three-quarter "
               "view) with face toward the viewer, eyes about one third from the top of the image, head and shoulders fully "
               "inside the frame with a little headroom, arms relaxed at the sides and hands out of frame.")
BACKGROUND = "Background: plain seamless flat light warm-grey studio background, no scenery, no props, no cast shadow."
LIGHTING = "Lighting: soft even front key light with a gentle rim light."
AVOID = ("Avoid: text, letters, logos, watermark, signature, border, frame, extra people, visible hands, cropped head, "
         "childlike or teenage features, photorealism, 3D render look.")
KEEP = ("Edit this image. Keep the exact same character: identical face shape, eye colour, hairstyle, hair colour, skin tone, "
        "outfit, accessories, pose, framing, camera angle, lighting, background and art style.")
EDIT_TAIL = "Do not add hands, props, text, tears streaming, or any new objects. Do not change the crop."

BASELINE = {  # v2 fix 1
    "soft": "gentle relaxed expression with a faint warm smile, attentive eyes looking at the viewer",
    "neutral": "calm neutral, mouth closed, attentive eyes looking at the viewer",
    "sharp": "composed, slightly intense gaze, mouth closed, eyes looking at the viewer",
}
EMOTIONS = {  # TESTING.md A2 with v2 fixes 2 and 3
    "happy": "a warm open smile showing a little of the upper teeth, eyes softly crinkled",
    "sad": "inner brows raised, eyes lowered and slightly glossy, mouth gently downturned",
    "angry": "brows drawn down and together, narrowed eyes, tight mouth",
    "surprised": 'eyebrows high, eyes wide open, mouth in a small open "o"',
    "thinking": "eyes looking up and to the side, brows relaxed with one slightly raised, curious pondering look",
    "embarrassed": "a blush across the cheeks and nose, an awkward small smile, eyes glancing away",
    "blink": "eyes fully closed and relaxed, otherwise identical to the original",
}
OFF_LIMITS = re.compile(r"\b(background|scenery|pose|posture|art style|style|photo\w*|realistic|3d|render)\b", re.I)
TINTED = re.compile(r"\b([a-z]+)-tinted ([a-z]+(?:-[a-z]+)?)( hair| bob| curls| waves)?", re.I)


@dataclass(frozen=True)
class CompiledPrompt:
    prompt: str
    warnings: list[str] = field(default_factory=list)

    @property
    def refused(self) -> bool:
        return any(w.startswith("REFUSED") for w in self.warnings)


def fix_compound_colours(text: str) -> str:
    """v2 fix 4: "a pink-tinted chestnut bob" → "a chestnut bob with a soft pink tint"."""
    return TINTED.sub(lambda m: f"{m.group(2)}{m.group(3) or ' hair'} with a soft {m.group(1).lower()} tint", text)


LENGTHS = {"chin": "chin-length", "shoulder": "shoulder-length", "buzz": "buzz-cut"}
VOCAB = {"coily": "tightly coiled natural hair"}  # rule 5: translate vocabulary literally


def hair_colour(colour: str, text: str) -> str:
    """v2 fix 4 on the structured colour: when the description names a compound for this colour ("pink-tinted
    chestnut" for `pink`), use the compound with its base colour first ("chestnut with a soft pink tint")."""
    for m in TINTED.finditer(text):
        if m.group(1).lower() == colour.lower() or f"{m.group(1)}-tinted {m.group(2)}".lower() == colour.lower():
            return f"{m.group(2).lower()} with a soft {m.group(1).lower()} tint"
    whole = TINTED.fullmatch(colour)
    return f"{whole.group(2)} with a soft {whole.group(1).lower()} tint" if whole else colour


def _sentence(text: str) -> str:
    t = text.strip()
    return t if not t or t.endswith((".", "!", "?")) else f"{t}."


def _article(word: str) -> str:
    return "an" if word[:1].lower() in "aeiou" or word.startswith("8") else "a"


class ImagePromptCompiler:
    def __init__(self, style_presets: Sequence[Mapping[str, Any]]) -> None:
        self.presets = {str(p["id"]): p for p in style_presets}

    def _style(self, appearance: Mapping[str, Any]) -> str:
        preset = self.presets.get(str(appearance.get("stylePresetId"))) or next(iter(self.presets.values()), None)
        fragment = str(preset["promptFragment"]).strip() if preset else ""
        return f"{_sentence(fragment)} {ADULT}".strip()

    @staticmethod
    def _refusal(age: Any) -> CompiledPrompt | None:
        if not isinstance(age, int | float) or age < 18:
            return CompiledPrompt("", ["REFUSED: the character must be an adult (18 or older)."])
        return None

    @staticmethod
    def subject(profile: Mapping[str, Any], appearance: Mapping[str, Any]) -> str:
        """Rule 2's subject block: a name-free description with age and role, then face → hair → eyes → outfit →
        accessories (at most 3), using only the given attribute values."""
        a: Mapping[str, Any] = appearance.get("attributes") or {}
        role = str(profile.get("role") or "").strip().rstrip(".")
        age = int(profile.get("age") or 0)
        head = f"{_article(str(age))} {age}-year-old {role[:1].lower()}{role[1:]}" if role else f"{_article(str(age))} {age}-year-old adult"
        lines = [f"{head[:1].upper()}{head[1:]}."]
        summary = fix_compound_colours(str(appearance.get("appearanceSummary") or ""))
        if summary:
            lines.append(_sentence(summary))
        body, face, hair, eyes = a.get("body") or {}, a.get("face") or {}, a.get("hair") or {}, a.get("eyes") or {}
        face_bits = [f"{face['shape']} face" if face.get("shape") else "", f"{body['skinTone']} skin" if body.get("skinTone") else ""]
        face_bits += [str(m) for m in face.get("marks") or []]
        if any(face_bits):
            lines.append("Face: " + ", ".join(b for b in face_bits if b) + ".")
        if hair:
            colour = hair_colour(str(hair.get("color") or ""), f"{appearance.get('appearanceSummary') or ''} "
                                                               f"{a.get('extraDetails') or ''}")
            length = str(hair.get("length") or "")
            style = str(hair.get("style") or "")
            bits = [LENGTHS.get(length, length), colour, VOCAB.get(style, style)]
            if hair.get("streakColor"):
                bits.append(f"a {hair['streakColor']} streak")
            if hair.get("fringe") and hair["fringe"] != "none":
                bits.append(f"{hair['fringe']} fringe")
            lines.append("Hair: " + ", ".join(b for b in bits if b) + ".")
        if eyes:
            eye = " ".join(x for x in (str(eyes.get("shape") or ""), str(eyes.get("color") or "")) if x)
            glasses = f", {eyes['glasses']} glasses" if eyes.get("glasses") and eyes["glasses"] != "none" else ""
            lines.append(f"Eyes: {eye} eyes{glasses}.")
        outfit = a.get("outfit") or {}
        details = fix_compound_colours(str(a.get("extraDetails") or ""))
        if outfit.get("archetype") or details:
            lines.append(f"Outfit: {outfit.get('archetype', 'everyday')} style" + (f"; {_sentence(details)}" if details else "."))
        acc = [str(x) for x in (a.get("accessories") or [])][:3]
        if acc:
            lines.append("Accessories: " + ", ".join(acc) + ".")
        return " ".join(lines)

    def base(self, profile: Mapping[str, Any], appearance: Mapping[str, Any], *, note: str | None = None) -> CompiledPrompt:
        """`note`: the wizard's "Doesn't look like them" hint, added to the subject as the user wrote it."""
        refused = self._refusal(profile.get("age"))
        if refused:
            return refused
        baseline = str(((appearance.get("attributes") or {}).get("face") or {}).get("baseline") or "neutral")
        expression = BASELINE.get(baseline, BASELINE["neutral"])
        subject = self.subject(profile, appearance)
        hint = " ".join(str(note or "").split())[:300]
        if hint:
            subject = f"{subject} Also: {_sentence(hint)}"
        prompt = "\n".join([self._style(appearance), "", f"Subject: {subject}", "",
                            COMPOSITION, f"Expression: {expression}.", BACKGROUND, LIGHTING, "", AVOID])
        return CompiledPrompt(prompt)

    def emotion_edit(self, profile: Mapping[str, Any], emotion: str) -> CompiledPrompt:
        refused = self._refusal(profile.get("age"))
        if refused:
            return refused
        if emotion not in EMOTIONS:
            raise ValueError(f"no edit instruction for {emotion!r}")
        return CompiledPrompt(f"{KEEP} Change ONLY the facial expression to: {EMOTIONS[emotion]}.\n{EDIT_TAIL}")

    def tweak(self, profile: Mapping[str, Any], text: str) -> CompiledPrompt:
        refused = self._refusal(profile.get("age"))
        if refused:
            return refused
        clean = " ".join(text.split())[:300]
        warnings = []
        if OFF_LIMITS.search(clean):
            warnings.append("The pose, background and art style stay as they are; that part of the tweak was ignored.")
        change = _sentence(clean) if clean else "Refine the details slightly."
        return CompiledPrompt(f"{KEEP} Apply ONLY this small change: {change} Keep the pose, background and art style.\n"
                              f"{EDIT_TAIL}", warnings)

    def sheet(self, profile: Mapping[str, Any], appearance: Mapping[str, Any]) -> CompiledPrompt:
        refused = self._refusal(profile.get("age"))
        if refused:
            return refused
        prompt = "\n".join([
            self._style(appearance), "",
            f"Character expression sheet of ONE character: {self.subject(profile, appearance)}",
            "A 2-row by 4-column grid of identical waist-up portraits, same outfit, same pose, same framing, same plain "
            "light warm-grey background in every cell, thin even gutters, no labels.",
            "Row 1: neutral, happy, sad, angry. Row 2: surprised, thinking, embarrassed, eyes closed.", "",
            "Avoid: text, numbers, captions, different outfits between cells, extra characters."])
        return CompiledPrompt(prompt)
